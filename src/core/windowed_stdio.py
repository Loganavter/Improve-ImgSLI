"""Stdio / faulthandler bootstrap for windowed (no-console) frozen apps.

PyInstaller ``--noconsole`` / ``pythonw`` leave ``sys.stdin`` / ``stdout`` /
``stderr`` as ``None``. Calling ``faulthandler.enable()`` then raises
``RuntimeError: sys.stderr is None`` and aborts startup before Qt.

The same startup-position hazard applies to the opt-in fault dump: it is
armed from ``__main__`` before Qt exists, so an unwritable path (Windows
``%TEMP%`` policies, a read-only dir, a directory where the log file should
be) must *disable the dump*, never kill startup. That warning is reported to
``core.startup_early_log`` as well: at this point nothing has attached a log
handler yet, and a windowed build's ``stderr`` is ``os.devnull``.
"""

from __future__ import annotations

import faulthandler
import logging
import os
import sys
import tempfile

from shared.debug_flags import env_flag as _env_flag
from shared.debug_flags import env_value as _env_value
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

#: The disabled-dump warning is reported once per process: the arming function is
#: called again on re-arm paths (and by tests), and the early file must not
#: collect a duplicate line.
_disabled_dump_reported = False


def _report_disabled_dump(path: str, exc: BaseException) -> None:
    """Emit the one "Fault dump disabled" warning to both sinks that exist here.

    This runs from ``__main__`` before ``setup_logging`` attaches a handler, and
    a windowed build points ``stderr`` at ``os.devnull`` -- so ``logger.warning``
    alone is invisible in exactly the build that needs the line. The early
    startup file (``core.startup_early_log``) is the same sink the stall reports
    use; the import is stdlib-only, so a lazy import at the failure point cannot
    pull Qt in.
    """
    global _disabled_dump_reported
    logger.warning(
        "Fault dump disabled: cannot open/wire %s (%s: %s)",
        path,
        type(exc).__name__,
        exc,
    )
    if _disabled_dump_reported:
        return
    _disabled_dump_reported = True
    try:
        from core.startup_early_log import write_error_record

        write_error_record(
            f"Fault dump disabled: cannot open/wire {path} "
            f"({type(exc).__name__}: {exc})"
        )
    except Exception:  # noqa: BLE001 (startup must survive any sink error)
        pass


def ensure_stdio() -> None:
    if sys.stdin is None:
        sys.stdin = open(os.devnull, "r", encoding="utf-8", errors="replace")
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="replace")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="replace")


def enable_faulthandler() -> None:
    # Opt-in hang dumps: set IMGSLI_FAULT_DUMP=1 (optional IMGSLI_FAULT_DUMP_FILE /
    # IMGSLI_FAULT_DUMP_INTERVAL). The default lands in the system temp dir
    # (portable — Windows has no POSIX temp dir); an explicit _FILE is used
    # verbatim.
    # Never raises — a path problem disables the dump with one warning instead
    # of aborting startup before Qt (call order in ``__main__``).
    if _env_flag("IMGSLI_FAULT_DUMP"):
        fault_dump_path = _env_value(
            "IMGSLI_FAULT_DUMP_FILE",
            os.path.join(tempfile.gettempdir(), "imgsli_fault_dump.log"),
        )
        try:
            fault_dump_file = open(fault_dump_path, "w", encoding="utf-8")
            faulthandler.enable(file=fault_dump_file, all_threads=True)
            try:
                fault_dump_interval = int(
                    _env_value("IMGSLI_FAULT_DUMP_INTERVAL", "15") or "15"
                )
            except (TypeError, ValueError):
                fault_dump_interval = 15
            faulthandler.dump_traceback_later(
                fault_dump_interval,
                repeat=True,
                file=fault_dump_file,
            )
        except Exception as exc:  # noqa: BLE001 (startup must survive any path error)
            _report_disabled_dump(fault_dump_path, exc)
        return

    try:
        # Needs a real OS fileno; skip quietly when stdio is a non-fd sink.
        if sys.stderr is None or not hasattr(sys.stderr, "fileno"):
            return
        sys.stderr.fileno()
        faulthandler.enable()
    except Exception:
        pass
