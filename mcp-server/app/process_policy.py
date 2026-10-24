"""Display/launch policy + process bookkeeping for the fallback launch path.

The live channel (``live.py``) answers most tool calls; when no instance is
attached the server still boots app processes, and that fallback path has two
documented defects this module fixes:

- **defect 2 — windows landed on the user's live desktop.** Detached launches
  inherited the session environment wholesale. On a Wayland session Qt ignores
  ``DISPLAY`` unless ``QT_QPA_PLATFORM=xcb`` is forced, so a spawn meant to be
  invisible put a real window on the user's screen. ``launch_env`` therefore
  always scrubs ``DISPLAY`` / ``WAYLAND_DISPLAY`` / ``XDG_SESSION_TYPE`` and
  defaults to the offscreen platform; a visible window requires the explicit
  ``IMGSLI_MCP_DISPLAY`` opt-in (e.g. a private ``:97`` Xvfb), never the
  session's own display.
- **defect 3 — a fallback boot clobbered the live app's log.** The app rewrites
  ``log.txt`` on every start, so a single fallback boot destroys the running
  instance's log for good. ``preserve_live_log`` copies it into the artifacts
  dir before any boot, and ``read_log`` serves that copy while a live instance
  is running.

Also hosts ``ProcessRegistry``: ``open_tab`` for a tab that already has a live
process must reuse it rather than spawn a second window.

``pid_alive`` answers "may the process still exist"; it uses ``kill(pid, 0)``
on POSIX but ``OpenProcess`` + ``GetExitCodeProcess`` on Windows, where
``os.kill`` is TerminateProcess in disguise. ``process_report`` answers
"what happened to it", which is what a failed control call must say: ``/proc``
can still expose a zombie's exit status/signal, and when it cannot the report
says so instead of inventing one.

Stdlib only, like the rest of ``mcp-server/app``.
"""

from __future__ import annotations

import os
import shutil
import signal
from pathlib import Path
from typing import Any

#: Explicit opt-in for a visible fallback window: the display to open it on.
DISPLAY_OPT_IN_ENV = "IMGSLI_MCP_DISPLAY"

#: Filename under the artifacts dir holding the pre-launch copy of ``log.txt``.
PRESERVED_LOG_NAME = "live-log.txt"

#: Keys scrubbed from every launch environment (defect 2).
_SESSION_DISPLAY_KEYS = ("DISPLAY", "WAYLAND_DISPLAY", "XDG_SESSION_TYPE")

#: Platform seam for the pid-liveness probe (module-level so tests can drive
#: either arm from either OS; see :func:`pid_alive`).
_IS_WINDOWS = os.name == "nt"

_QUERY_LIMITED = 0x1000  # PROCESS_QUERY_LIMITED_INFORMATION
_STILL_ACTIVE = 259  # GetExitCodeProcess value while the process runs
_ERROR_ACCESS_DENIED = 5  # OpenProcess: it exists, we may not query it


def launch_env(visible: bool = False) -> dict[str, str]:
    """Environment for a fallback app process — headless unless opted in.

    Default (``visible=False``) is the offscreen platform with every display
    variable scrubbed, so a fallback boot can never put a window on the user's
    desktop (defect 2: the session is Wayland, where Qt ignores ``DISPLAY``
    unless ``QT_QPA_PLATFORM=xcb`` is forced — an inherited environment opened
    windows on the live desktop).

    ``visible=True`` asks for a window, but the request is honoured only when
    ``IMGSLI_MCP_DISPLAY`` names a display (e.g. a private Xvfb ``:97``); then
    ``DISPLAY`` is set to exactly that value, the platform is forced to ``xcb``,
    and ``WAYLAND_DISPLAY`` / ``XDG_SESSION_TYPE`` are scrubbed so Qt cannot
    fall back to the session's Wayland compositor. Without the opt-in a visible
    request degrades to headless rather than inheriting the session display.
    """
    env = dict(os.environ)
    display = (env.get(DISPLAY_OPT_IN_ENV) or "").strip()
    for key in _SESSION_DISPLAY_KEYS:
        env.pop(key, None)
    if visible and display:
        env["DISPLAY"] = display
        env["QT_QPA_PLATFORM"] = "xcb"
    else:
        env["QT_QPA_PLATFORM"] = "offscreen"
    return env


def pid_alive(pid: int | None) -> bool:
    """Liveness check that never signals the process — on either platform.

    POSIX: ``kill(pid, 0)`` is the probe. ``PermissionError`` means the process
    exists but belongs to someone else (still alive); any other ``OSError``
    means it is gone.

    Windows: ``os.kill`` is *not* a probe — CPython lowers every signal other
    than CTRL_C_EVENT / CTRL_BREAK_EVENT to OpenProcess + TerminateProcess, so
    ``os.kill(pid, 0)`` kills the target with exit code 0. This arm uses
    ``OpenProcess`` + ``GetExitCodeProcess`` instead: ``STILL_ACTIVE`` means
    alive, and a failed open means alive only for ``ERROR_ACCESS_DENIED`` (the
    process exists, we may not query it) — anything else (an invalid pid) means
    gone.

    This is a deliberate duplicate of ``core.control.discovery.is_pid_alive``:
    ``mcp-server/app`` is stdlib-only and must keep running without the app
    package (which pulls in PySide6), so it cannot import the app's copy. Keep
    the two arms in step — ``tests/devtools/test_control_discovery.py`` and
    ``tests/devtools/test_mcp_server.py`` pin both to the same table.
    """
    try:
        candidate = int(pid)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    if candidate <= 0:
        return False
    if _IS_WINDOWS:
        import ctypes  # noqa: PLC0415 - Windows-only import cost

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(_QUERY_LIMITED, False, candidate)
        if not handle:
            return kernel32.GetLastError() == _ERROR_ACCESS_DENIED
        try:
            code = ctypes.c_ulong(0)
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return bool(ok) and code.value == _STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(candidate, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _proc_stat_fields(pid: int) -> list[str] | None:
    """``/proc/<pid>/stat`` fields after the comm field, or ``None``.

    ``comm`` may contain spaces and parentheses, so the split starts after the
    last ``)``; index 0 is then the state letter (field 3).
    """
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    _head, _sep, rest = raw.rpartition(")")
    fields = rest.split()
    return fields or None


def _decode_wait_status(code: int) -> tuple[int | None, int | None]:
    """``(signal, exit_code)`` from a wait-status-shaped ``exit_code``.

    Same encoding as ``waitpid``: a non-zero low 7 bits are the signal, else the
    upper byte is the exit code.
    """
    low = code & 0x7F
    if low and low != 0x7F:
        return low, None
    return None, (code >> 8) & 0xFF


def _signal_name(number: int | None) -> str | None:
    if number is None:
        return None
    try:
        return signal.Signals(number).name
    except ValueError:  # pragma: no cover - realtime signal, no name
        return None


def process_report(pid: int | None) -> dict[str, Any]:
    """What this process can *honestly* say about *pid* after a connection died.

    A sibling is not the app's parent: it cannot ``waitpid`` an exit status, and
    a crashed app is usually reaped long before anyone looks. What is left is
    ``/proc`` — a zombie still carries its wait status (signal + exit code), a
    reaped one is simply gone, and a sandboxed pid from another namespace does
    not resolve at all. The report says which of those happened and never
    guesses a signal it could not read.

    Keys: ``pid``, ``state`` (``no-pid`` | ``alive`` | ``zombie`` | ``gone`` |
    ``unobservable``), ``signal``, ``exit_code``, ``observable`` and a
    one-sentence ``detail`` for the user-facing message.
    """
    report: dict[str, Any] = {
        "pid": pid,
        "state": "no-pid",
        "signal": None,
        "exit_code": None,
        "observable": False,
        "detail": (
            "the app's pid is not recorded in the discovery pointer (a sandboxed "
            "or detached instance), so its exit status is not observable"
        ),
    }
    try:
        candidate = int(pid)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return report
    if candidate <= 0:
        return report
    report["pid"] = candidate

    fields = _proc_stat_fields(candidate)
    if fields is None:
        if pid_alive(candidate):
            report["state"] = "unobservable"
            report["detail"] = (
                f"pid {candidate} exists but could not be inspected (/proc is "
                "unavailable or permission denied), so its exit status is not "
                "observable from this process"
            )
        else:
            report["state"] = "gone"
            report["detail"] = (
                f"pid {candidate} is gone; its exit status and signal are not "
                "observable from this process (only the app's parent can reap them)"
            )
        return report

    state = fields[0]
    if state != "Z":
        report["state"] = "alive"
        report["detail"] = (
            f"pid {candidate} still exists (state {state}); the process itself "
            "has not exited"
        )
        return report

    report["state"] = "zombie"
    try:
        code = int(fields[49])  # field 52: exit_code, wait-status shaped
    except (IndexError, ValueError):
        report["detail"] = (
            f"pid {candidate} is a zombie; its exit status could not be read"
        )
        return report
    number, exit_code = _decode_wait_status(code)
    report["signal"] = number
    report["exit_code"] = exit_code
    report["observable"] = number is not None or exit_code is not None
    if number is not None:
        name = _signal_name(number)
        label = f"{name} (signal {number})" if name else f"signal {number}"
        report["detail"] = f"pid {candidate} exited via {label}"
    else:
        report["detail"] = f"pid {candidate} exited with status {exit_code}"
    return report


class ProcessRegistry:
    """Fallback-launched app processes, keyed by the tab they were opened for.

    ``open_tab`` consults this first: a tab that already has a live process is
    reused (the result gains ``reused: true``) instead of spawning a second
    window. A pid whose process is gone is dropped on read, so a crashed launch
    never blocks a later one.
    """

    def __init__(self) -> None:
        self._pids: dict[str, int] = {}

    def adopt(self, tab: str, pid: int) -> None:
        self._pids[str(tab)] = int(pid)

    def live_pid(self, tab: str) -> int | None:
        """The live pid for ``tab``, or ``None`` (dropping a dead entry)."""
        pid = self._pids.get(str(tab))
        if pid is None:
            return None
        if pid_alive(pid):
            return pid
        del self._pids[str(tab)]
        return None

    def release(self, tab: str) -> None:
        self._pids.pop(str(tab), None)


def preserve_live_log(
    artifacts_dir: Path | str, *, source: Path | str | None = None
) -> str | None:
    """Copy the app's current ``log.txt`` aside before a boot clobbers it.

    Returns the path of the copy, or ``None`` when there is no log to preserve.
    ``source`` (keyword-only) overrides the app data dir's ``log.txt`` so callers
    can point at an explicit data dir; the app's own log is the default.

    The app truncates ``log.txt`` on every start, so a fallback boot silently
    destroys a running instance's log — the reason ``read_log`` serves this copy
    while a live instance is attached (defect 3).
    """
    if source is None:
        from .backend import app_data_dir  # lazy: backend imports this module

        origin = app_data_dir() / "log.txt"
    else:
        origin = Path(source)
    if not origin.is_file():
        return None
    destination_dir = Path(artifacts_dir)
    try:
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / PRESERVED_LOG_NAME
        shutil.copy2(origin, destination)
    except OSError:
        return None
    return str(destination)
