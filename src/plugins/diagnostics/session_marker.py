"""Was the PREVIOUS run closed cleanly? One marker file, one verdict.

The app never learned that its last session ended abnormally: a task-manager
kill, a power cut, a segfault or the startup failure in the owner's 2026-10-28
log all look the same from the outside — the user reopens the app and nothing
offers to tell us what happened. This module is the missing detector.

The mechanism is deliberately dumb and local (no network, no service):

* at startup the app writes ``<app-data>/run/last-session.json`` with its pid,
  the wall clock, the version, the log path and (where the OS has one) the boot
  id — ``clean: false``;
* a normal exit rewrites the same file with ``clean: true``;
* the next startup classifies what it finds: ``none`` (no marker, or a clean
  one), ``concurrent`` (that pid is still alive — another instance is running,
  not a crash) or ``unclean``.

Two false positives are handled explicitly, because a nagging dialog is worse
than a missed report:

* **another instance** — the pid is alive, so nothing crashed;
* **a reboot since then / a recycled pid** — a different boot id means the
  recorded process cannot still be the one running; and a marker older than
  :data:`CONCURRENT_WINDOW_S` is never treated as "someone is running".

Pure stdlib, no Qt: the caller decides how to offer the report.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: Marker file name inside the app's ``run`` directory.
MARKER_NAME = "last-session.json"
#: How long a live pid is trusted as "another instance" rather than a recycled id.
CONCURRENT_WINDOW_S = 24 * 60 * 60
#: How many lines of the previous log a report carries.
LOG_TAIL_LINES = 120
#: Upper bound on the fault-dump tail (a hang dump repeats forever).
FAULT_TAIL_BYTES = 8000


def marker_path() -> Path:
    """Where the marker lives: the app-data ``run`` dir (same root as the socket)."""
    from core.control.app_paths import app_data_dir

    return app_data_dir() / "run" / MARKER_NAME


def boot_id() -> str:
    """A stable id for THIS boot, or ``""`` where the OS has no such thing.

    Linux exposes it read-only; Windows/macOS do not, and an absent value must
    never be read as "a different boot" (that would turn every clean marker into
    a false alarm), so the classifier only compares two non-empty ids.
    """
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _now_iso(now: float | None = None) -> str:
    return datetime.fromtimestamp(
        time.time() if now is None else now, tz=timezone.utc
    ).isoformat(timespec="seconds")


@dataclass(frozen=True)
class PreviousSession:
    """What the marker says about the session before this one."""

    path: Path
    clean: bool
    pid: int | None
    started_at: str
    version: str
    boot_id: str
    log_file: str
    fault_file: str
    raw_mtime: float

    @property
    def age_s(self) -> float:
        return max(0.0, time.time() - self.raw_mtime)

    def as_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "started_at": self.started_at,
            "version": self.version,
            "log_file": self.log_file,
            "fault_file": self.fault_file,
            "marker_age_s": round(self.age_s, 1),
        }


def _read_marker(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def read_previous(*, path: Path | None = None) -> PreviousSession | None:
    """The previous session's marker, or ``None`` when there is none.

    An unreadable/corrupt marker answers ``None`` (nothing to promise) — never a
    guess: a half-written file must not be reported as a crash.
    """
    target = Path(path) if path is not None else marker_path()
    data = _read_marker(target)
    if data is None:
        return None
    try:
        mtime = target.stat().st_mtime
    except OSError:
        return None
    pid_raw = data.get("pid")
    try:
        pid = int(pid_raw) if pid_raw is not None else None
    except (TypeError, ValueError):
        pid = None
    return PreviousSession(
        path=target,
        clean=bool(data.get("clean")),
        pid=pid,
        started_at=str(data.get("started_at") or ""),
        version=str(data.get("version") or ""),
        boot_id=str(data.get("boot_id") or ""),
        log_file=str(data.get("log_file") or ""),
        fault_file=str(data.get("fault_file") or ""),
        raw_mtime=mtime,
    )


def classify(previous: PreviousSession | None) -> str:
    """``"none"`` | ``"concurrent"`` | ``"unclean"`` for one marker."""
    if previous is None or previous.clean:
        return "none"
    current_boot = boot_id()
    if previous.boot_id and current_boot and previous.boot_id != current_boot:
        # A different boot: the recorded process is gone, whatever the pid says.
        return "unclean"
    if previous.pid is not None and previous.age_s <= CONCURRENT_WINDOW_S:
        try:
            from core.control.discovery import is_pid_alive

            if is_pid_alive(previous.pid):
                return "concurrent"
        except Exception:
            pass
    return "unclean"


def begin_session(
    *,
    path: Path | None = None,
    log_file: str | Path | None = None,
    fault_file: str | Path | None = None,
    version: str = "",
    now: float | None = None,
) -> Path:
    """Write the ``clean: false`` marker for THIS session. Never raises."""
    target = Path(path) if path is not None else marker_path()
    payload = {
        "schema": 1,
        "pid": os.getpid(),
        "started_at": _now_iso(now),
        "version": str(version or ""),
        "boot_id": boot_id(),
        "log_file": str(log_file or ""),
        "fault_file": str(fault_file or ""),
        "clean": False,
    }
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, target)
    except Exception:
        pass
    return target


def mark_clean(*, path: Path | None = None) -> bool:
    """Rewrite the marker as a clean exit. Never raises; ``False`` = nothing to do."""
    target = Path(path) if path is not None else marker_path()
    data = _read_marker(target)
    if data is None:
        return False
    data["clean"] = True
    data["ended_at"] = _now_iso()
    try:
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, target)
        return True
    except Exception:
        return False


def _tail_lines(path: str | Path, *, lines: int = LOG_TAIL_LINES) -> list[str]:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    kept = [line for line in text.splitlines() if line.strip()]
    return kept[-lines:]


def _tail_text(path: str | Path, *, limit: int = FAULT_TAIL_BYTES) -> str:
    try:
        blob = Path(path).read_bytes()
    except Exception:
        return ""
    return blob[-limit:].decode("utf-8", "replace").strip()


def failure_payload(previous: PreviousSession) -> dict[str, Any]:
    """The ``failure`` dict a diagnostics report is built with.

    Shape matches what the excepthook passes (``type`` / ``message`` / extra
    keys), so the report dialog, the redactor and the issue title treat it like
    any other failure.
    """
    when = previous.started_at or "unknown time"
    payload: dict[str, Any] = {
        "type": "UncleanShutdown",
        "message": (
            f"the previous session (started {when}"
            + (f", version {previous.version}" if previous.version else "")
            + ") ended without a normal exit"
        ),
        "previous_session": previous.as_dict(),
        "log_tail": _tail_lines(previous.log_file),
    }
    fault = _tail_text(previous.fault_file)
    if fault:
        # A faulthandler dump is the closest thing to a traceback a SIGSEGV
        # leaves behind; the report is the only place a user would ever see it.
        payload["fault_dump_tail"] = fault
    return payload


def offer_is_suppressed(settings: Any | None = None) -> bool:
    """Whether the user asked not to be offered the report again."""
    if settings is None:
        try:
            from plugins.settings.manager import SettingsManager
            from core.plugin_system.settings import SETTINGS_APP, SETTINGS_ORG

            settings = SettingsManager(SETTINGS_ORG, SETTINGS_APP)
        except Exception:
            return False
    try:
        store = settings.settings if hasattr(settings, "settings") else settings
        store.beginGroup("diagnostics")
        try:
            value = store.value("offer_unclean_report", True)
        finally:
            store.endGroup()
    except Exception:
        return False
    if isinstance(value, str):
        return value.strip().lower() in ("false", "0", "no", "off")
    return not bool(value)


def suppress_offer(settings: Any | None = None) -> None:
    """Persist "do not offer again". Best effort, never raises."""
    try:
        store = settings.settings if hasattr(settings, "settings") else settings
        store.beginGroup("diagnostics")
        try:
            store.setValue("offer_unclean_report", False)
            store.sync()
        finally:
            store.endGroup()
    except Exception:
        pass


__all__ = [
    "CONCURRENT_WINDOW_S",
    "FAULT_TAIL_BYTES",
    "LOG_TAIL_LINES",
    "MARKER_NAME",
    "PreviousSession",
    "begin_session",
    "boot_id",
    "classify",
    "failure_payload",
    "mark_clean",
    "marker_path",
    "offer_is_suppressed",
    "read_previous",
    "suppress_offer",
]


def _platform_note() -> str:  # pragma: no cover - documentation only
    return f"marker={marker_path()} platform={sys.platform}"
