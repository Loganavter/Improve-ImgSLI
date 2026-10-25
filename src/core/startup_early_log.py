"""Line-per-record startup log that exists before ``setup_logging`` runs.

``main.entry``, the module-scope imports, ``QApplication`` creation, the RHI /
D3D11 probe (307-374 ms cold) and ``MainWindow`` construction all run
**before** ``core.bootstrap._configure_logging`` attaches a handler. A
``logger.info`` line emitted there is dropped by an unconfigured logger, and a
windowed (``--noconsole``) build points ``stderr`` at ``os.devnull`` -- so that
window is *invisible*, not absent.

This module owns the fallback file: ``<app data dir>/startup_early.log``, next
to ``log.txt``. It is created at import and **only** when a startup-diagnostics
flag is on (``IMGSLI_STARTUP_TRACE`` or ``IMGSLI_STALL_WATCH``, or their
``BLINKTABLE_`` spellings). With both off no directory is touched, no file is
created, and every function here is a no-op -- the default run is unchanged.

The file is opened ``w`` once per traced run (wiped), then appended one record
at a time and closed again: no long-lived handle, no Qt object, no
``setup_logging`` dependency. Nothing here raises -- a read-only or unusable
data directory disables the sink silently.

Time base: ``time.perf_counter()`` captured at import, i.e. the earliest point
a portable Python process can observe itself. ``src/__main__.py`` imports this
module (through :mod:`core.startup_trace`) before its heavy imports, so
``main.entry`` is the +0 ms line and every later offset is "ms since startup".
Interpreter start-up before that import is not measurable portably and is
excluded by construction.

See ``docs/dev/LOGGING.md`` (Early sink section).
"""

from __future__ import annotations

import os
import sys
import threading
import time

from shared.debug_flags import env_flag as _env_flag
from shared.debug_flags import env_value as _env_value

#: File name inside the app-data log directory (same directory as ``log.txt``).
FILE_NAME = "startup_early.log"

#: Hard bounds: one record is capped so a runaway stack dump cannot grow the
#: file per line, and the file itself is capped so a traced run left open for
#: hours cannot accumulate an unbounded number of stall reports.
_MAX_RECORD_CHARS = 4096
_MAX_RECORDS = 1000

#: Earliest observable point of this process (see module docstring).
_T0 = time.perf_counter()

_lock = threading.RLock()
_last_at: float | None = None
_logging_ready = False


def _stamp(total_ms: float, delta_ms: float) -> str:
    return f"+{total_ms:9.1f}ms (+{delta_ms:8.1f}ms)"


def _offsets() -> tuple[float, float]:
    """Total and delta offsets in ms, both from ``time.perf_counter()``."""
    global _last_at
    now = time.perf_counter()
    with _lock:
        last = _last_at
        _last_at = now
    total_ms = (now - _T0) * 1000.0
    delta_ms = total_ms if last is None else (now - last) * 1000.0
    return total_ms, delta_ms


def debug_requested() -> bool:
    """True when a startup-diagnostics flag asks for the early file."""
    return _env_flag("IMGSLI_STARTUP_TRACE") or _env_flag("IMGSLI_STALL_WATCH")


def _app_data_dir(app_name: str) -> str:
    """Per-OS app-data directory, mirroring ``sli_ui_toolkit.core.logging``.

    Mirrored, not imported, on purpose: importing the toolkit pulls Qt in, and
    this module runs *before* Qt exists -- the cost would be attributed to the
    +0 ms mark and would move a heavy import into the pre-Qt window. The mirror
    is pinned against the toolkit original by
    ``tests/runtime/test_startup_early_log.py``; update both together.
    """
    if sys.platform == "win32":
        app_data_dir = os.getenv("APPDATA") or os.path.expanduser("~")
        return os.path.join(app_data_dir, app_name)
    if sys.platform == "darwin":
        return os.path.join(
            os.path.expanduser("~/Library/Application Support"), app_name
        )
    xdg_data_home = os.getenv("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return os.path.join(xdg_data_home, app_name)


def _log_directory() -> str | None:
    """Resolve the app-data log directory without forcing the log-dir migration.

    ``core.log_dir_migration`` aliases ``…/ImproveImgSLI`` to ``…/BlinkTable`` on
    the first start of a renamed build, and it only does so while the new
    directory is *absent*. Creating the new directory here at import time would
    make that migration report ``kept`` and silently orphan the user's existing
    ``log.txt`` tree, so write into the legacy directory when it is the only one
    on disk: the migration later makes both spellings the same tree. A fresh
    install has neither directory, and there is nothing to preserve.
    """
    try:
        from core.log_names import APP_LOGGER_NAME, LEGACY_LOG_DIR_NAME

        new_dir = _app_data_dir(APP_LOGGER_NAME)
        legacy_dir = _app_data_dir(LEGACY_LOG_DIR_NAME)
    except Exception:
        return None
    if not new_dir:
        return None
    try:
        if os.path.isdir(new_dir):
            return new_dir
        if os.path.isdir(legacy_dir):
            return legacy_dir
    except Exception:
        return None
    return new_dir


class _EarlySink:
    """One append-only text file: opened ``w`` once, then one append per record."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._records = 0
        self._capped = False

    @classmethod
    def create(cls) -> _EarlySink | None:
        """Build the sink from the environment; ``None`` when it is off/unusable."""
        if not debug_requested():
            return None
        directory = _log_directory()
        if not directory:
            return None
        path = os.path.join(directory, FILE_NAME)
        try:
            os.makedirs(directory, exist_ok=True)
            # ``w``: every traced run starts from an empty file.
            with open(path, "w", encoding="utf-8", errors="replace"):
                pass
        except Exception:
            return None
        return cls(path)

    def write(self, record: str) -> bool:
        """Append one bounded record; ``False`` when nothing was written."""
        text = record[:_MAX_RECORD_CHARS].rstrip("\n")
        with _lock:
            if self._records >= _MAX_RECORDS:
                if self._capped:
                    return False
                self._capped = True
                text = (
                    f"{_stamp(*_offsets())}  [early log] record cap "
                    f"({_MAX_RECORDS}) reached; further records dropped"
                )
            try:
                # Append + close per record: a killed process loses nothing that
                # was already reported, and no handle survives into the window.
                with open(self.path, "a", encoding="utf-8", errors="replace") as handle:
                    handle.write(text + "\n")
            except Exception:
                return False
            self._records += 1
        return True


#: The one sink for this process; created at import, ``None`` when the flags
#: are off (default) or the data directory is unusable.
_sink: _EarlySink | None = _EarlySink.create()


def path() -> str | None:
    """Path of the early file in use, or ``None`` when the sink is off."""
    return _sink.path if _sink is not None else None


def write_mark(name: str, **fields: object) -> None:
    """Append one phase mark (``+total (+delta)  name  key=value…``). No-op when off."""
    sink = _sink
    if sink is None:
        return
    try:
        total_ms, delta_ms = _offsets()
        suffix = "".join(
            f"  {key}={value}" for key, value in fields.items() if value is not None
        )
        sink.write(f"{_stamp(total_ms, delta_ms)}  {name}{suffix}")
    except Exception:
        pass


def write_record(text: str) -> bool:
    """Append a free-form record (a stall report) under one timestamp.

    Returns ``True`` only when the record actually landed in the early file, so
    a caller can fall back to the ordinary logger otherwise.
    """
    sink = _sink
    if sink is None:
        return False
    try:
        total_ms, delta_ms = _offsets()
        lines = (text.rstrip("\n") or " ").splitlines()
        record = f"{_stamp(total_ms, delta_ms)}  {lines[0]}"
        for line in lines[1:]:
            record += "\n" + line
        return sink.write(record)
    except Exception:
        return False


def logging_ready() -> bool:
    """True once ``setup_logging`` has run (``ctx.logging_ready`` phase)."""
    return _logging_ready


def mark_logging_ready() -> None:
    """The ordinary log now exists: it owns diagnostics from here on."""
    global _logging_ready
    _logging_ready = True


def selftest_sleep() -> float:
    """Test hook: hold the GUI thread while the watchdog is armed.

    ``IMGSLI_STARTUP_EARLY_SELFTEST_SLEEP_MS`` makes a traced launch block
    before logging is configured, so a deliberate ``[stall]`` proves it lands
    in the early file instead of being dropped. Off when unset; capped at 10 s
    so a stray value cannot wedge a real launch.
    """
    if _sink is None:
        return 0.0
    raw = (_env_value("IMGSLI_STARTUP_EARLY_SELFTEST_SLEEP_MS", "") or "").strip()
    try:
        ms = float(raw)
    except (TypeError, ValueError):
        return 0.0
    ms = min(max(ms, 0.0), 10_000.0)
    if ms <= 0:
        return 0.0
    time.sleep(ms / 1000.0)
    return ms / 1000.0


def _reload_for_tests() -> str | None:
    """Rebuild the sink from the CURRENT environment (tests only)."""
    global _sink, _last_at, _logging_ready
    with _lock:
        _sink = _EarlySink.create()
        _last_at = None
        _logging_ready = False
    return path()
