"""Client + adapter for the app's live control socket (Phase 2 channel).

Phase 1 (``backend.py``) can only boot throwaway headless apps; this module
attaches to an *already running* instance over the frozen in-app control
protocol and proxies the MCP tool surface onto it:

- **Transport** — a Qt QLocalServer unix socket in the app. Newline-delimited
  JSON: one request ``{"id", "method", "params"}`` per line, one response
  ``{"id", "ok": true, "result"}`` / ``{"id", "ok": false, "error", "hint"}``.
- **Discovery** — ``IMGSLI_MCP_CONTROL_SOCKET`` (explicit socket path) →
  ``IMGSLI_CONTROL_DIR`` (explicit dir) → ``$XDG_RUNTIME_DIR`` when it is
  writable **and private** (owner, no group/other access — the app's own rule,
  see :func:`control_dirs`) → ``<app data dir>/run``. The socket is
  ``control.sock`` and a pointer file ``instance.json`` holds
  ``{pid, socket, started, version, uid}``; a pointer recording another ``uid``
  is not a live instance.
  A pointer is stale only when its socket is unusable: the pid is a hint, not
  the verdict (Flatpak apps live in their own PID namespace), and a socket
  nobody listens on is "no live instance" — never a user-visible error.
- **Degrading cleanly** — the app refuses connections from another uid (its own
  SO_PEERCRED check, not ours) and may close the socket at any time; every
  failure surfaces as ``LiveUnavailable`` so the caller falls back to Phase 1.
- **A death is not an absence** — an EOF *after* the request left this process,
  with the socket node no longer answering, means the app died under it. That
  failure carries the request it was handling (a redacted digest — never a
  secret), the pid and whatever ``/proc`` can still say about it (a zombie's
  signal; "not observable" when reaped or sandboxed). A timeout keeps its own
  honest wording: a slow app is not a dead one.

Stdlib only, like the rest of ``mcp-server/app``.
"""

from __future__ import annotations

import json
import os
import re
import socket
import stat
import sys
import time
from pathlib import Path
from typing import Any, Mapping

from .process_policy import pid_alive, process_report

#: Wall-clock budget for one request/response round trip (seconds).
DEFAULT_TIMEOUT_S = 5.0

#: How many extra attempts a *read* makes after a transport timeout (plan P2:
#: reads retry exactly once). Mutations never retry — the app may already have
#: applied the edit, so a silent second attempt risks double-applying it.
READ_RETRY_BUDGET = 1

#: Transport-failure phrasings, kept distinguishable in the message text so a
#: caller can tell "the app never saw the request" from "the request was sent
#: but no reply came back" (plan P2). Never invent a third kind.
NOT_SENT = "not sent"
SENT_NO_REPLY = "sent, no reply"

#: How long to stop re-attaching after a transport failure (seconds). Keeps the
#: fallback path from paying a failed connect on every single tool call.
DEFAULT_RETRY_COOLDOWN_S = 2.0

#: Names inside a control dir (frozen by the app-side implementation).
CONTROL_SOCKET_NAME = "control.sock"
INSTANCE_POINTER_NAME = "instance.json"
#: The app's own record of the request it was handling (``core.control.server``
#: writes it before the handler runs and removes it once the reply is sent). A
#: note that outlives the process is where it died; on a clean stop there is
#: none, so this is the difference between "app died" and "app is not running".
INFLIGHT_NOTE_NAME = "inflight.json"

#: Explicit overrides, highest priority first.
SOCKET_OVERRIDE_ENV = "IMGSLI_MCP_CONTROL_SOCKET"
CONTROL_DIR_ENV = "IMGSLI_CONTROL_DIR"

#: Cap on ignored lines while waiting for our own response id.
_MAX_SKIPPED_LINES = 100

#: Cap on the request digest echoed in a death report (mirrors the app's note).
_PARAM_SUMMARY_LIMIT = 400
_PARAM_VALUE_LIMIT = 48

#: Parameter NAMES whose value is never echoed — the request that kills the app
#: can carry a token (``run_action`` forwards free-form params).
_SECRET_KEY_RE = re.compile(
    r"(?i)(api[_-]?key|token|secret|passw|credential|authori[sz]|cookie|bearer|private[_-]?key)"
)

#: Values that look like a credential, whatever the parameter is called.
_SECRET_VALUE_RE = re.compile(
    r"(?i)^(sk-|pk-|ghp_|gho_|ghs_|github_pat_|xox[abp]-|bearer[ =:]|ey[A-Za-z0-9_-]{8,}\.)"
)

#: Budget for the liveness probe that runs only when the pointer's pid cannot
#: be verified. A unix-socket connect returns immediately; the timeout only
#: bounds a pathological listener backlog.
PID_PROBE_TIMEOUT_S = 0.25


class LiveUnavailable(Exception):
    """No live instance answered: socket missing/stale, refused, or closed.

    The caller falls back to Phase 1; this never reaches the user as an error —
    except for a mutation whose request was already on the wire (see ``sent`` /
    ``timeout``), which the backend must not paper over with a fallback.

    ``sent`` is True only once the request bytes left this process (a failure in
    ``connect``/``send`` is ``not sent``); ``timeout`` marks a read deadline
    expiry specifically (the reads' one retry is scoped to timeouts); ``died``
    marks an EOF *after* the send — the app closed the connection instead of
    answering, which (with the socket node gone) means the process died under
    the request. ``method``/``request_summary`` name what was in flight and
    ``process`` is the ``process_report`` the client could read at that moment.
    """

    def __init__(
        self,
        message: str,
        hint: str | None = None,
        *,
        sent: bool = False,
        timeout: bool = False,
        died: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.sent = bool(sent)
        self.timeout = bool(timeout)
        self.died = bool(died)
        #: The request that was in flight (filled in by ``LiveClient._call_once``).
        self.method: str | None = None
        self.request_summary: str | None = None
        #: ``process_policy.process_report`` for the app's pid, when it can be read.
        self.process: dict[str, Any] | None = None
        #: True when the app demonstrably outlived the connection (it still
        #: answers its socket, or its pid is alive): the *channel* broke.
        self.app_alive: bool | None = None


class LiveError(Exception):
    """The live app answered ``ok: false`` — a real, user-visible tool failure."""

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _is_socket(path: Path) -> bool:
    try:
        return stat.S_ISSOCK(path.stat().st_mode)
    except OSError:
        return False


def _read_pointer(directory: Path) -> dict[str, Any] | None:
    """The discovery pointer's JSON object, or ``None`` when unusable."""
    try:
        data = json.loads(
            (directory / INSTANCE_POINTER_NAME).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _pointer_pid(data: Mapping[str, Any] | None) -> int | None:
    pid = (data or {}).get("pid")
    if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0:
        return int(pid)
    return None


def pointer_pid(socket_path: Path | str) -> int | None:
    """The pid the pointer next to *socket_path* records, or ``None``.

    A hint, never a verdict (see ``_pointer_socket``): it is what lets a death
    report name the process and ask ``/proc`` what happened to it.
    """
    return _pointer_pid(_read_pointer(Path(socket_path).parent))


def _read_note(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("method"), str):
        return None
    return data


def read_inflight_note(socket_path: Path | str) -> dict[str, Any] | None:
    """The app's record of the request it was handling, when one is left over.

    Written and cleared by ``core.control.server`` (the name is duplicated here
    because this package is stdlib-only). Present after a crash, absent after a
    clean stop or a finished request.
    """
    return _read_note(Path(socket_path).parent / INFLIGHT_NOTE_NAME)


def _param_value(value: Any) -> str:
    """One digest fragment: short scalars verbatim, secrets and shapes masked."""
    if isinstance(value, str):
        if _SECRET_VALUE_RE.match(value.strip()):
            return "<redacted>"
        shown = (
            value
            if len(value) <= _PARAM_VALUE_LIMIT
            else value[:_PARAM_VALUE_LIMIT] + "…"
        )
        return repr(shown)
    if isinstance(value, dict):
        return f"{{{len(value)} keys}}"
    if isinstance(value, (list, tuple, set)):
        return f"[{len(value)} items]"
    if isinstance(value, (bool, int, float)) or value is None:
        return repr(value)
    return f"<{type(value).__name__}>"


def summarize_request_params(params: Any) -> str:
    r"""A bounded, secret-free digest of one request's params (``k=v, ...``).

    The same rule the app applies to its own ``inflight.json`` note
    (``core.control.server.summarize_request_params`` — this package cannot
    import it): secret-named parameters become ``<redacted>``,
    credential-shaped values are masked wherever they appear, strings are
    truncated and containers are reduced to their shape.
    """
    if not isinstance(params, dict) or not params:
        return ""
    parts: list[str] = []
    for key, value in params.items():
        name = str(key)
        if _SECRET_KEY_RE.search(name):
            parts.append(f"{name}=<redacted>")
        else:
            parts.append(f"{name}={_param_value(value)}")
    summary = ", ".join(parts)
    if len(summary) > _PARAM_SUMMARY_LIMIT:
        summary = summary[:_PARAM_SUMMARY_LIMIT] + "…"
    return summary


def death_message(
    *,
    method: str,
    summary: str | None,
    report: Mapping[str, Any],
    socket_answers: bool,
    died: bool = True,
) -> str:
    """The user-facing sentence for a connection that died under a request.

    Four distinguishable cases, never merged into "no live instance":

    * the socket still answers → the process is running, the *connection* broke;
    * the pid is still there but the socket does not answer → the channel died,
      whether the process did is not observable from here;
    * EOF and the process is gone (or a zombie whose status was readable) →
      "the app died", plus the signal/exit code when ``/proc`` still had it;
    * no readable pid → say the exit status is not observable, do not guess.
    """
    request = f"request {method!r}"
    if summary:
        request += f" ({summary})"
    detail = str(report.get("detail") or "").strip()
    state = report.get("state")
    if socket_answers:
        return (
            f"{SENT_NO_REPLY}: the control socket closed while {request} was in "
            "flight, but the app still answers on it — the process is running and "
            "the connection was interrupted"
        )
    if not died:
        return (
            f"{SENT_NO_REPLY}: the control connection failed while {request} was in "
            "flight; whether the app is still running is not observable from this "
            "process"
        )
    if state == "alive":
        return (
            f"{SENT_NO_REPLY}: the control socket closed and no longer answers while "
            f"{request} was in flight — {detail}"
        )
    return f"{SENT_NO_REPLY}: the app died while {request} was in flight — {detail}"


def evidence_sentence(evidence: Mapping[str, Any]) -> str:
    """One sentence about a stopped instance, from its on-disk evidence.

    ``evidence`` is ``LiveBackend.death_evidence()``: the app's own in-flight
    note (when it died inside a request) and ``process_report`` for its pid. It
    says "died" only where the evidence supports it — a pid that still exists
    is reported as a broken channel, not a death.
    """
    request = evidence.get("request") or {}
    report = evidence.get("process") or {}
    detail = str(report.get("detail") or "").strip()
    method = request.get("method") if isinstance(request, Mapping) else None
    if method:
        text = f"the app died while handling request {method!r}"
        summary = request.get("summary")
        if summary:
            text += f" ({summary})"
        at = request.get("at")
        if at:
            text += f" at {at}"
        return f"{text} — {detail}" if detail else text
    if report.get("state") == "alive":
        return f"the control channel stopped answering — {detail}"
    return f"the app stopped without a request in flight — {detail}"


def app_data_dir(env: Mapping[str, str] | None = None) -> Path:
    """Per-OS app data dir (``~/.local/share/ImproveImgSLI`` on Linux).

    The ONLY copy of this rule in ``mcp-server`` (``backend.app_data_dir``
    delegates here); ``env`` lets discovery be evaluated for an explicit
    environment instead of the process one.
    """
    source = dict(os.environ) if env is None else env
    if sys.platform.startswith("linux"):
        base = source.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:  # pragma: no cover - Windows
        base = source.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "ImproveImgSLI"


def _is_private_dir(path: Path) -> bool:
    """True iff *path* is a directory we own with no group/other access.

    The same predicate the app applies in
    ``core.control.discovery._is_private_dir`` (the app owns that copy because
    ``core`` pulls in PySide6 and this package is stdlib-only). Discovery must
    agree in BOTH directions: a shared dir the app refuses must not be probed
    here either, or the client looks in a place the app never publishes in and
    silently falls back to headless (measured 2026-10-21).
    """
    try:
        info = path.stat()
    except OSError:
        return False
    if not stat.S_ISDIR(info.st_mode):
        return False
    if info.st_uid != os.getuid():
        return False
    return stat.S_IMODE(info.st_mode) & 0o077 == 0


def control_dirs(env: Mapping[str, str] | None = None) -> list[Path]:
    """Control dirs to probe, in the app's own priority order.

    ``[<private, writable $XDG_RUNTIME_DIR>, <app data dir>/run]`` — the FIRST
    entry is exactly what ``core.control.discovery.runtime_dir()`` returns when
    no explicit override is set, which is what makes the two sides agree. The
    second entry stays as a fallback for a socket left in the data dir by an
    earlier env (the app only ever writes in one of them).

    ``XDG_RUNTIME_DIR`` is deliberately NOT ``expanduser``-ed: the app does not
    expand it either, and two derivations of one rule may not differ.
    """
    source = dict(os.environ) if env is None else env
    candidates: list[Path] = []
    runtime = (source.get("XDG_RUNTIME_DIR") or "").strip()
    if runtime:
        candidate = Path(runtime)
        if (
            candidate.is_dir()
            and os.access(candidate, os.W_OK)
            and _is_private_dir(candidate)
        ):
            candidates.append(candidate)
    candidates.append(app_data_dir(source) / "run")
    return candidates


def _socket_answers(path: Path, *, timeout: float = PID_PROBE_TIMEOUT_S) -> bool:
    """True when something accepts a connection on ``path`` right now.

    A bare connect is enough: it proves a listener owns the node, which is the
    only fact staleness is allowed to rest on (see ``_pointer_socket``). Any
    ``OSError`` — missing node, ``ECONNREFUSED``, not a socket — means there is
    nothing to attach to.
    """
    try:
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    except OSError:  # pragma: no cover - platform without AF_UNIX
        return False
    try:
        probe.settimeout(timeout)
        probe.connect(str(path))
    except OSError:
        return False
    finally:
        probe.close()
    return True


def _pointer_uid(data: Mapping[str, Any] | None) -> int | None:
    """The pointer's recorded owning uid, or ``None`` when it does not say.

    Absence is not a refusal (pointers written before the field existed, or by
    a sandbox that maps uids, stay usable); a present integer that is not ours
    is.
    """
    uid = (data or {}).get("uid")
    if isinstance(uid, int) and not isinstance(uid, bool):
        return int(uid)
    return None


def _pointer_socket(directory: Path) -> tuple[Path | None, bool]:
    """``(socket, stale)`` for a control dir with an ``instance.json`` pointer.

    ``socket`` is the pointer's ``socket`` field, falling back to the sibling
    ``control.sock``. ``stale`` means "nothing usable here": the pointer is
    reported as "no live instance" and must not be trusted.

    A foreign ``uid`` is stale before anything else is considered: the app
    publishes the pointer for its own user only, and handing another user's
    socket to the request layer would earn a bare ``SO_PEERCRED`` refusal
    instead of the honest "no live instance".

    The pid is a *hint, never the verdict*. A Flatpak-installed app runs in its
    own PID namespace, so ``pid_alive`` on the host may raise
    ``ProcessLookupError`` for a perfectly live sandboxed app (the pointer
    records the sandbox-local pid) or see a foreign pid as ``PermissionError``.
    Judging the pointer stale from that alone hides a working socket and the
    server answers "no live instance" while the app is up and connectable.
    Staleness therefore requires a dead-looking pid **and** a probe connect that
    fails: a dead pid with no socket stays "no live instance", a socket nobody
    listens on is not live either (the attach probe fails), but an unverifiable
    pid whose socket answers is used.
    """
    pointer = directory / INSTANCE_POINTER_NAME
    if not pointer.is_file():
        return None, False
    data = _read_pointer(directory)
    if data is None:
        return None, False
    owner = _pointer_uid(data)
    if owner is not None and owner != os.getuid():
        return None, True
    field = data.get("socket")
    if isinstance(field, str) and field.strip():
        candidate = Path(field.strip()).expanduser()
    else:
        candidate = directory / CONTROL_SOCKET_NAME
    pid = _pointer_pid(data)
    if pid is not None and not pid_alive(pid) and not _socket_answers(candidate):
        return None, True
    return candidate, False


def _socket_in_dir(directory: Path) -> Path | None:
    """The live control socket inside ``directory``, or ``None``."""
    if not directory.is_dir():
        return None
    candidate, stale = _pointer_socket(directory)
    if stale:
        return None
    if candidate is None:
        candidate = directory / CONTROL_SOCKET_NAME
    return candidate if _is_socket(candidate) else None


def discover_socket(env: Mapping[str, str] | None = None) -> Path | None:
    """Locate a live instance's control socket, or ``None`` when there is none.

    Priority: ``IMGSLI_MCP_CONTROL_SOCKET`` (an explicit socket path, honoured
    alone), ``IMGSLI_CONTROL_DIR`` (an explicit control dir, honoured alone),
    then :func:`control_dirs` — ``$XDG_RUNTIME_DIR`` **when it is private** (the
    app's rule, not merely "writable") and the app-data ``run`` dir. An override
    that points at nothing plausible yields ``None`` — the caller treats that as
    "no live instance", not an error.
    """
    source = dict(os.environ) if env is None else env

    explicit = (source.get(SOCKET_OVERRIDE_ENV) or "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        return path if _is_socket(path) else None

    override_dir = (source.get(CONTROL_DIR_ENV) or "").strip()
    if override_dir:
        return _socket_in_dir(Path(override_dir).expanduser())

    for directory in control_dirs(source):
        found = _socket_in_dir(directory)
        if found is not None:
            return found
    return None


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class LiveClient:
    """One connection to the app's control socket.

    ``call`` raises ``LiveUnavailable`` on any transport failure (missing or
    stale socket, refused/closed connection, timeout, unparseable frame) and
    ``LiveError`` when the app answers ``ok: false`` — the caller's cue to fall
    back or to surface the app's own error message respectively.
    """

    def __init__(
        self,
        socket_path: Path | str,
        *,
        timeout: float = DEFAULT_TIMEOUT_S,
        pid: int | None = None,
    ) -> None:
        self.socket_path = Path(socket_path)
        self.timeout = float(timeout)
        #: The pid the discovery pointer named, if any — a hint for the death
        #: report, never a verdict (a sandboxed pointer pid may not resolve here).
        self.pid = pid
        self._sock: socket.socket | None = None
        self._buffer = b""
        self._counter = 0

    # -- transport ---------------------------------------------------------

    def _connect(self) -> socket.socket:
        if self._sock is not None:
            return self._sock
        if not self.socket_path.exists():
            raise LiveUnavailable(f"{NOT_SENT}: no control socket at {self.socket_path}")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(self.timeout)
            sock.connect(str(self.socket_path))
        except OSError as exc:
            sock.close()
            raise LiveUnavailable(
                f"{NOT_SENT}: cannot connect to the control socket: {exc}"
            )
        self._sock = sock
        self._buffer = b""
        return sock

    def _read_message(self, sock: socket.socket, request_id: Any) -> dict:
        deadline = time.monotonic() + self.timeout
        skipped = 0
        while True:
            if b"\n" in self._buffer:
                line, self._buffer = self._buffer.split(b"\n", 1)
            else:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise LiveUnavailable(
                        f"{SENT_NO_REPLY}: timed out waiting for the control socket",
                        sent=True,
                        timeout=True,
                    )
                sock.settimeout(remaining)
                try:
                    chunk = sock.recv(65536)
                except socket.timeout:
                    raise LiveUnavailable(
                        f"{SENT_NO_REPLY}: timed out waiting for the control socket",
                        sent=True,
                        timeout=True,
                    )
                except OSError as exc:
                    raise LiveUnavailable(
                        f"{SENT_NO_REPLY}: control socket read failed: {exc}", sent=True
                    )
                if not chunk:
                    raise LiveUnavailable(
                        f"{SENT_NO_REPLY}: the control socket was closed by the app",
                        sent=True,
                        died=True,
                    )
                self._buffer += chunk
                continue
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line.decode("utf-8", "replace"))
            except ValueError:
                message = None
            if isinstance(message, dict) and message.get("id") == request_id:
                return message
            # Not our response: a notification or a stale frame. Ignore it, but
            # never loop forever on a stream that only emits noise.
            skipped += 1
            if skipped > _MAX_SKIPPED_LINES:
                raise LiveUnavailable(
                    f"{SENT_NO_REPLY}: no response with our request id from the control socket",
                    sent=True,
                )

    def call(self, method: str, params: dict | None = None, *, retry_on_timeout: bool = False) -> dict:
        """Send one request, return its ``result`` object.

        ``retry_on_timeout=True`` (reads) makes exactly ``READ_RETRY_BUDGET``
        extra attempt after a *transport timeout*; a mutation leaves it False so
        a timed-out edit is never re-sent. Every other transport fault raises
        immediately. Raises ``LiveUnavailable`` (transport) or ``LiveError``
        (app-reported failure with the app's own message and hint).
        """
        attempts = 1 + READ_RETRY_BUDGET if retry_on_timeout else 1
        last: LiveUnavailable | None = None
        for _ in range(attempts):
            try:
                return self._call_once(method, params)
            except LiveUnavailable as exc:
                last = exc
                if not (retry_on_timeout and exc.timeout):
                    raise
            # a timed-out socket is unusable; ``_call_once`` closed it, so the
            # next attempt reconnects from scratch.
        assert last is not None  # only reachable via the timeout branch above
        raise last

    def _call_once(self, method: str, params: dict | None) -> dict:
        self._counter += 1
        request_id = self._counter
        payload = json.dumps(
            {"id": request_id, "method": method, "params": params or {}},
            ensure_ascii=False,
        )
        try:
            sock = self._connect()
            sock.sendall(payload.encode("utf-8") + b"\n")
        except LiveUnavailable:
            self.close()
            raise
        except OSError as exc:
            self.close()
            raise LiveUnavailable(f"{NOT_SENT}: control socket write failed: {exc}")
        try:
            message = self._read_message(sock, request_id)
        except LiveUnavailable as exc:
            self.close()
            raise self._explain_transport(exc, method, params)
        except OSError as exc:
            self.close()
            failure = LiveUnavailable(
                f"{SENT_NO_REPLY}: control socket {self.socket_path} failed: {exc}",
                sent=True,
            )
            raise self._explain_transport(failure, method, params)
        if message.get("ok") is not True:
            raise LiveError(str(message.get("error") or f"{method} failed"), _hint(message))
        result = message.get("result")
        if result is None:
            return {}
        if not isinstance(result, dict):
            raise LiveError(f"{method} returned a non-object result", "report an app-side bug")
        return result

    def _explain_transport(
        self, exc: LiveUnavailable, method: str, params: dict | None
    ) -> LiveUnavailable:
        """Attach *what was in flight* and, for a mid-call drop, the death report.

        Only a failure that left the request on the wire can be a death: a
        connect/send failure says nothing about the app (it may simply not be
        running), and a timeout is a slow app, not a dead one — both keep their
        own wording. For a post-send failure the socket is probed once (a live
        app that still answers means the *connection* broke, not the process)
        and ``/proc`` is read for the pid, when the pointer named one.
        """
        exc.method = method
        exc.request_summary = summarize_request_params(params)
        if not exc.sent or exc.timeout:
            return exc
        report = process_report(self.pid)
        exc.process = report
        answers = bool(exc.died and _socket_answers(self.socket_path))
        exc.app_alive = answers or report.get("state") == "alive"
        exc.message = death_message(
            method=method,
            summary=exc.request_summary,
            report=report,
            socket_answers=answers,
            died=exc.died,
        )
        return exc

    def alive(self) -> bool:
        """True when a live instance answers ``ping`` on this socket."""
        try:
            self.call("ping")
        except (LiveUnavailable, LiveError):
            return False
        return True

    def close(self) -> None:
        sock, self._sock = self._sock, None
        self._buffer = b""
        if sock is not None:
            try:
                sock.close()
            except OSError:  # pragma: no cover - best effort
                pass


def _hint(message: dict) -> str | None:
    hint = message.get("hint")
    return str(hint) if hint else None


def action_enabled(row: Mapping[str, Any]) -> bool:
    """``enabled`` for a ``list_actions`` row, degrading to True when absent.

    The frozen P2 row shape is ``{..., enabled: bool, reason: str|null}``; the
    app-side descriptor is landing in parallel, so a row that omits the key (or
    carries ``null``) must read as *enabled*, never crash.
    """
    value = row.get("enabled")
    return True if value is None else bool(value)


def action_reason(row: Mapping[str, Any]) -> str | None:
    """``reason`` for a ``list_actions`` row, degrading to ``None`` when absent."""
    value = row.get("reason")
    return str(value) if value else None


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class LiveBackend:
    """Proxies the MCP tool surface onto a live instance.

    ``try_attach`` finds/keeps a connection (never raising); the per-tool
    methods shape the request and normalise the response into exactly the result
    shape the Phase-1 backend returns, so ``backend.py`` can swap sources without
    changing its contract. Every result carries ``source: "live"``; mutations
    that cannot carry a Phase-1 key (``launched`` / ``pid``) add ``live: true``.

    All app-reported failures surface as ``LiveError``; all transport failures
    as ``LiveUnavailable`` — the caller's fall back signal.
    """

    def __init__(
        self,
        *,
        client: LiveClient | None = None,
        socket_path: Path | str | None = None,
        timeout: float = DEFAULT_TIMEOUT_S,
        env: Mapping[str, str] | None = None,
        retry_cooldown_s: float = DEFAULT_RETRY_COOLDOWN_S,
    ) -> None:
        self._client = client
        self.socket_path = Path(socket_path) if socket_path is not None else None
        self.timeout = float(timeout)
        self._env = env
        self._retry_cooldown_s = float(retry_cooldown_s)
        self._retry_after = 0.0

    # -- attach / detach ---------------------------------------------------

    def try_attach(self) -> LiveClient | None:
        """A live client, or ``None`` — never raises (any fault is "absent")."""
        try:
            if self._client is not None and self._client.alive():
                return self._client
            self.close()
            path = self.socket_path or discover_socket(self._env)
            if path is None:
                return None
            candidate = LiveClient(path, timeout=self.timeout, pid=pointer_pid(path))
            if candidate.alive():
                self._client = candidate
                return candidate
            candidate.close()
        except Exception:  # defensive: the attach probe must never raise
            return None
        return None

    def client_if_alive(self) -> LiveClient | None:
        """``try_attach``, throttled after a failure to avoid thrashing."""
        if time.monotonic() < self._retry_after:
            return None
        return self.try_attach()

    def note_failure(self) -> None:
        """Record a transport failure and pause re-attaching briefly."""
        self.close()
        if self._retry_cooldown_s > 0:
            self._retry_after = time.monotonic() + self._retry_cooldown_s

    # -- after the fact ----------------------------------------------------

    def _control_dirs(self) -> list[Path]:
        """Control dirs to inspect when there is no socket to ask.

        Mirrors ``discover_socket``'s precedence exactly, so evidence is scoped
        to the instance the caller is talking about: an explicit socket or
        control dir wins *alone* (never mixing in another instance's leftovers),
        otherwise the app's own candidates (``control_dirs``).
        """
        if self.socket_path is not None:
            return [Path(self.socket_path).parent]
        env = dict(os.environ) if self._env is None else self._env
        explicit_socket = (env.get(SOCKET_OVERRIDE_ENV) or "").strip()
        if explicit_socket:
            return [Path(explicit_socket).expanduser().parent]
        explicit_dir = (env.get(CONTROL_DIR_ENV) or "").strip()
        if explicit_dir:
            return [Path(explicit_dir).expanduser()]
        return control_dirs(env)

    def death_evidence(self) -> dict[str, Any] | None:
        """What is on disk about an instance that stopped answering.

        ``None`` when nothing suggests an app was ever there (no pointer, no
        note): then "no live instance" is the plain truth and the caller keeps
        its shorter wording. Otherwise the app's own in-flight note (only a
        crash leaves one) and what ``/proc`` can say about its pid. Read-only —
        the app clears both artifacts on a clean start/stop.
        """
        note: dict[str, Any] | None = None
        pid: int | None = None
        for directory in self._control_dirs():
            if note is None:
                note = _read_note(directory / INFLIGHT_NOTE_NAME)
            if pid is None:
                pid = _pointer_pid(_read_pointer(directory))
            if note is not None and pid is not None:
                break
        if note is None and pid is None:
            return None
        if note is not None:
            note_pid = _pointer_pid(note)
            if note_pid is not None:
                pid = note_pid
        return {"request": note, "pid": pid, "process": process_report(pid)}

    def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            client.close()

    @property
    def attached(self) -> bool:
        return self._client is not None

    # -- request plumbing --------------------------------------------------

    #: Wire methods that are *reads*: they may retry exactly once on a
    #: transport timeout (plan P2). Anything not listed is a mutation and
    #: never retries, so a timed-out edit is never silently re-sent.
    READ_METHODS = frozenset(
        {
            "ping",
            "list_actions",
            "list_sessions",
            "get_state",
            "get_canvas_scene",
            "read_log",
            "query_trace",
            "dump_ui_layout",
            "list_surfaces",
            "ui_elements",
            "ui_nav_state",
            "jobs_list",
        }
    )

    def _request(self, method: str, params: dict, client: LiveClient | None) -> dict:
        active = client or self.client_if_alive()
        if active is None:
            raise LiveUnavailable(f"{NOT_SENT}: no live instance is attached")
        return active.call(method, params, retry_on_timeout=method in self.READ_METHODS)

    @staticmethod
    def _rows(result: dict, key: str) -> list[dict]:
        rows = result.get(key)
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

    # -- read tools --------------------------------------------------------

    def list_actions(
        self, *, client: LiveClient | None = None, query: str | None = None, owner_tab: str | None = None
    ) -> dict:
        params: dict[str, Any] = {}
        if query:
            params["query"] = query
        if owner_tab:
            params["owner_tab"] = owner_tab
        rows = [
            {
                "action_id": row.get("action_id"),
                "label": row.get("label"),
                "owner_tab": row.get("owner_tab"),
                "topic": row.get("topic"),
                "shortcut": row.get("shortcut"),
                "enabled": action_enabled(row),
                "reason": action_reason(row),
            }
            for row in self._rows(self._request("list_actions", params, client), "actions")
        ]
        return {"count": len(rows), "actions": rows, "source": "live"}

    def list_sessions(self, *, client: LiveClient | None = None) -> dict:
        rows = [
            {
                "id": row.get("id"),
                "session_type": row.get("session_type"),
                "title": row.get("title"),
                "active": bool(row.get("active")),
            }
            for row in self._rows(self._request("list_sessions", {}, client), "sessions")
        ]
        return {"count": len(rows), "sessions": rows, "source": "live"}

    def get_canvas_scene(
        self, *, client: LiveClient | None = None, tab: str | None = None
    ) -> dict:
        params: dict[str, Any] = {}
        if tab:
            params["tab"] = tab
        result = self._request("get_canvas_scene", params, client)
        payload = {key: value for key, value in result.items() if key != "source"}
        payload["source"] = "live"
        return payload

    def get_state(self, *, client: LiveClient | None = None, path: str | None = None) -> dict:
        params = {"path": path} if path else {}
        result = self._request("get_state", params, client)
        return {
            "path": result.get("path", path),
            "state": result.get("state"),
            "source": "live",
        }

    def read_log(
        self, *, client: LiveClient | None = None, n: int = 200, level: str | None = None
    ) -> dict:
        params: dict[str, Any] = {"n": int(n)}
        if level:
            params["level"] = level
        result = self._request("read_log", params, client)
        lines = [
            {"n": row.get("n"), "level": row.get("level"), "text": row.get("text")}
            for row in self._rows(result, "lines")
        ]
        return {
            "path": str(result.get("path") or ""),
            "total_lines": int(result.get("total_lines") or len(lines)),
            "returned": len(lines),
            "lines": lines,
            "source": "live",
        }

    def query_trace(
        self, *, client: LiveClient | None = None, filter: str | None = None, n: int = 100
    ) -> dict:
        params: dict[str, Any] = {"n": int(n)}
        if filter:
            params["filter"] = filter
        result = self._request("query_trace", params, client)
        records = [row for row in result.get("records") or [] if isinstance(row, dict)]
        return {
            "path": str(result.get("path") or ""),
            "total_records": int(result.get("total_records") or len(records)),
            "returned": len(records),
            "records": records,
            "source": "live",
        }

    def dump_ui_layout(
        self, *, client: LiveClient | None = None, tab: str | None = None, out: str | None = None
    ) -> dict:
        params: dict[str, Any] = {}
        if tab:
            params["tab"] = tab
        if out:
            params["out"] = out
        result = self._request("dump_ui_layout", params, client)
        return {
            "path": str(result.get("path") or out or ""),
            "tab": result.get("tab", tab),
            "windows": int(result.get("windows") or 0),
            "node_count": int(result.get("node_count") or 0),
            "source": "live",
        }

    def list_surfaces(self, *, client: LiveClient | None = None) -> dict:
        rows = [
            {
                "name": row.get("name"),
                "description": row.get("description", ""),
                "isolated": bool(row.get("isolated")),
                # The app computes both (``core.control.discovery.live_surfaces``);
                # ``capturable`` is the difference between "drivable after
                # open_tab" and "grab it right now". Absent means the app did
                # not claim it — never invent a capability.
                "live": bool(row.get("live", False)),
                "capturable": bool(row.get("capturable", False)),
            }
            for row in self._rows(self._request("list_surfaces", {}, client), "surfaces")
        ]
        return {"count": len(rows), "surfaces": rows, "source": "live"}

    # -- mutating tools ----------------------------------------------------

    def open_tab(self, *, client: LiveClient | None = None, tab: str) -> dict:
        result = self._request("open_tab", {"tab": tab}, client)
        return {
            "ran": bool(result.get("ran", True)),
            "tab": result.get("tab", tab),
            "live": True,
            "source": "live",
        }

    def run_action(
        self,
        *,
        client: LiveClient | None = None,
        action_id: str,
        params: dict[str, Any] | None = None,
        expect: dict[str, Any] | None = None,
        tab: str | None = None,
    ) -> dict:
        wire: dict[str, Any] = {"action_id": action_id}
        if params is not None:
            wire["params"] = params
        if expect is not None:
            wire["expect"] = expect
        if tab:
            wire["tab"] = tab
        result = self._request("run_action", wire, client)
        payload = {
            "ran": bool(result.get("ran", True)),
            "action_id": result.get("action_id", action_id),
            "tab": result.get("tab", tab),
        }
        # A scene command answers with its evidence; carry it through verbatim
        # instead of flattening it into a boolean "ran".
        for key in ("scene_command", "params", "changed", "changed_count", "verified", "failure"):
            if key in result:
                payload[key] = result[key]
        payload["live"] = True
        payload["source"] = "live"
        return payload

    def set_scene_commands(
        self,
        *,
        client: LiveClient | None = None,
        commands: list[dict],
        verify: bool = True,
        tab: str | None = None,
    ) -> dict:
        wire: dict[str, Any] = {"commands": commands, "verify": bool(verify)}
        if tab:
            wire["tab"] = tab
        result = self._request("set_scene_commands", wire, client)
        payload = {key: value for key, value in result.items() if key != "source"}
        payload["source"] = "live"
        return payload

    def open_folder(
        self,
        *,
        client: LiveClient | None = None,
        path: str,
        tab: str | None = None,
        slot: int | None = None,
        side: str | None = None,
    ) -> dict:
        params: dict[str, Any] = {"path": path}
        if tab:
            params["tab"] = tab
        if slot is not None:
            params["slot"] = int(slot)
        if side:
            params["side"] = side
        result = self._request("open_folder", params, client)
        payload = {
            "ran": bool(result.get("ran", True)),
            "path": str(result.get("path") or path),
            "routed": bool(result.get("routed", True)),
            "live": True,
            "source": "live",
        }
        if result.get("tab"):
            payload["tab"] = str(result["tab"])
        if result.get("images") is not None:
            payload["images"] = int(result["images"])
        return payload

    def open_file(
        self, *, client: LiveClient | None = None, path: str, tab: str | None = None
    ) -> dict:
        """Route one file into the running app's accepting tab (see open_file)."""
        params: dict[str, Any] = {"path": path}
        if tab:
            params["tab"] = tab
        result = self._request("open_file", params, client)
        return {
            "opened": bool(result.get("opened", True)),
            "path": str(result.get("path") or path),
            "tab": str(result.get("tab") or ""),
            "count": int(result.get("count") or 1),
            "source": "live",
        }

    def open_properties(
        self, *, client: LiveClient | None = None, path: str
    ) -> dict:
        """Show the app's image-properties dialog for *path* (non-modal)."""
        result = self._request("open_properties", {"path": path}, client)
        return {
            "opened": bool(result.get("opened", True)),
            "path": str(result.get("path") or path),
            "dialog": str(result.get("dialog") or ""),
            "source": "live",
        }

    def set_theme(self, *, client: LiveClient | None = None, theme: str) -> dict:
        result = self._request("set_theme", {"theme": theme}, client)
        return {
            "theme": str(result.get("theme") or theme),
            "persisted": bool(result.get("persisted", True)),
            "applies_on": str(result.get("applies_on") or "now"),
            "live": True,
            "source": "live",
        }

    def set_language(self, *, client: LiveClient | None = None, language: str) -> dict:
        result = self._request("set_language", {"language": language}, client)
        return {
            "language": str(result.get("language") or language),
            "persisted": bool(result.get("persisted", True)),
            "applies_on": str(result.get("applies_on") or "now"),
            "live": True,
            "source": "live",
        }

    def set_setting(
        self, *, client: LiveClient | None = None, key: str, value: str
    ) -> dict:
        """Write one whitelisted setting; ``previous`` stays ``null`` when unset."""
        result = self._request("set_setting", {"key": key, "value": value}, client)
        previous = result.get("previous")
        return {
            "key": str(result.get("key") or key),
            "value": str(result.get("value") or value),
            "applied": bool(result.get("applied", False)),
            "persisted": bool(result.get("persisted", True)),
            "previous": None if previous is None else str(previous),
            "source": "live",
        }

    def capture_surface(
        self,
        *,
        client: LiveClient | None = None,
        surface: str | None = None,
        theme: str | None = None,
        out: str | None = None,
    ) -> dict:
        """Proxy ``capture_live`` and keep the app's capture provenance.

        ``surface`` is optional: without it the app grabs its active window
        (and refuses honestly when there is none — never another surface).

        ``theme``/``out`` are NOT sent: the live handler takes only ``what``
        and always writes to the app's artifacts dir with the window's own
        theme. The result says so through ``options_applied`` instead of
        echoing a request value that had no effect.

        An empty ``path`` means the live app answered without a file (e.g. it
        returned inline data this adapter does not save yet) — honest, not fake.
        """
        params: dict[str, Any] = {}
        if surface:
            params["what"] = surface
        result = self._request("capture_live", params, client)
        method = result.get("method")
        rhi_layers = result.get("rhi_layers")
        size: list[int] | None = None
        raw_size = result.get("size")
        if isinstance(raw_size, (list, tuple)) and len(raw_size) == 2:
            try:
                size = [int(raw_size[0]), int(raw_size[1])]
            except (TypeError, ValueError):
                size = None
        rhi_count: int | None = None
        if rhi_layers is not None:
            try:
                rhi_count = int(rhi_layers)
            except (TypeError, ValueError):
                rhi_count = None
        what = str(result.get("what") or surface or "")
        unavailable = [
            name
            for name, value in (
                ("what", what),
                ("method", method),
                ("size", size),
                ("rhi_layers", rhi_count),
            )
            if value is None or value == ""
        ]
        return {
            "surface": str(surface or ""),
            "what": what,
            "path": str(result.get("path") or ""),
            "method": None if method is None else str(method),
            "size": size,
            "rhi_layers": rhi_count,
            "theme": None,
            "live": True,
            "source": "live",
            "options_applied": [],
            "unavailable": unavailable,
        }

    def press_keys(
        self, *, client: LiveClient | None = None, keys: str, target: str | None = None
    ) -> dict:
        """Inject keyboard input (live-only; there is no headless analogue).

        ``target`` names an element id (``ui_elements``) so the keys reach a
        widget the window focus chain never gives them -- a canvas, whose
        zoom/pan keys are its own. Without it, the running app's focus widget
        receives them (the historical behaviour).

        ``activated`` and ``focus_is_ours`` are the app's own measurements of
        whether the keys could land (the same two ``nav_key`` reports): the
        window is made OS-active first, and a key handed to a background window
        is dropped by the window system. They are passed through as the app sent
        them -- ``None`` when it did not report them -- because coercing the
        answer would make a dropped key look delivered.
        """
        params: dict[str, Any] = {"keys": keys}
        if target:
            params["target"] = target
        result = self._request("press_keys", params, client)
        pressed = [str(item) for item in result.get("pressed") or []]
        activated = result.get("activated")
        focus_is_ours = result.get("focus_is_ours")
        return {
            "pressed": pressed,
            "count": int(result.get("count", len(pressed))),
            "target": str(result.get("target") or ""),
            "activated": activated if isinstance(activated, bool) else None,
            "focus_is_ours": focus_is_ours if isinstance(focus_is_ours, bool) else None,
            "source": "live",
        }

    # -- element targeting (live-only) -------------------------------------

    @staticmethod
    def _element(row: dict) -> dict:
        """One inventory row, normalised to the declared element shape."""
        raw_properties = row.get("properties")
        properties: dict[str, Any] = {}
        if isinstance(raw_properties, dict):
            properties = {
                str(key): value
                for key, value in raw_properties.items()
                if isinstance(value, (str, int, float, bool))
            }
        return {
            "id": str(row.get("id") or ""),
            "role": str(row.get("role") or ""),
            "label": str(row.get("label") or ""),
            "rect": list(row.get("rect") or []),
            "screen_rect": list(row.get("screen_rect") or []),
            "window": str(row.get("window") or ""),
            "owner_tab": row.get("owner_tab"),
            "action_id": row.get("action_id"),
            "enabled": bool(row.get("enabled")),
            "visible": bool(row.get("visible")),
            # An older app emits no bag; the key is still present (empty) so
            # the declared element shape never changes under a client.
            "properties": properties,
        }

    def ui_elements(
        self,
        *,
        client: LiveClient | None = None,
        scope: str | None = None,
        include_disabled: bool | None = None,
        role: str | None = None,
        label: str | None = None,
        properties: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> dict:
        params: dict[str, Any] = {}
        if scope:
            params["scope"] = scope
        if include_disabled:
            params["include_disabled"] = bool(include_disabled)
        if role:
            params["role"] = role
        if label:
            params["label"] = label
        if properties:
            params["properties"] = dict(properties)
        if limit is not None:
            params["limit"] = int(limit)
        result = self._request("ui_elements", params, client)
        rows = [self._element(row) for row in self._rows(result, "elements")]
        total = result.get("total")
        return {
            "count": int(result.get("count") or len(rows)),
            "total": int(total) if total is not None else len(rows),
            "window_count": int(result.get("window_count") or 0),
            "elements": rows,
            "source": "live",
        }

    def ui_nav_state(self, *, client: LiveClient | None = None) -> dict:
        """The live keyboard-navigation model (live-only; no headless analogue).

        Sections (ordered), the Qt focus widget, the last keyboard-granted
        widget and every open in-window overlay with the children Qt could
        focus but no section owns. Use it together with ``nav_key`` to judge
        whether a control is reachable by keyboard at all.
        """
        result = self._request("ui_nav_state", {}, client)
        return {**result, "source": "live"}

    def nav_key(
        self, *, client: LiveClient | None = None, keys: str, anchor: str | None = None
    ) -> dict:
        """Deliver keys through the app's own keyboard-navigation model.

        Unlike ``press_keys`` (one event aimed at one widget), this reports
        which layer took each key and how focus moved. ``anchor`` names an
        element id to focus first, with the app's own focus-reason policy.
        """
        params: dict[str, Any] = {"keys": keys}
        if anchor:
            params["anchor"] = anchor
        result = self._request("nav_key", params, client)
        # ``activated`` is reported because the app's navigation is inert while
        # the window is not OS-active: false means the keys were measured
        # against an app a real keyboard could not have reached either.
        return {**result, "source": "live"}

    def ui_click(
        self,
        *,
        client: LiveClient | None = None,
        id: str,
        button: str | None = None,
        count: int | None = None,
    ) -> dict:
        params: dict[str, Any] = {"id": id}
        if button:
            params["button"] = button
        if count:
            params["count"] = int(count)
        result = self._request("ui_click", params, client)
        return {
            "clicked": bool(result.get("clicked", True)),
            "id": str(result.get("id") or id),
            "rect": list(result.get("rect") or []),
            "screen_rect": list(result.get("screen_rect") or []),
            "target": str(result.get("target") or ""),
            "surface": str(result.get("surface") or ""),
            "source": "live",
        }

    def ui_hover(self, *, client: LiveClient | None = None, id: str) -> dict:
        result = self._request("ui_hover", {"id": id}, client)
        return {
            "hovered": bool(result.get("hovered", True)),
            "id": str(result.get("id") or id),
            "rect": list(result.get("rect") or []),
            "target": str(result.get("target") or ""),
            "source": "live",
        }

    def ui_focus(self, *, client: LiveClient | None = None, id: str) -> dict:
        result = self._request("ui_focus", {"id": id}, client)
        return {
            "focused": bool(result.get("focused", True)),
            "id": str(result.get("id") or id),
            "rect": list(result.get("rect") or []),
            "target": str(result.get("target") or ""),
            "focus_widget": str(result.get("focus_widget") or ""),
            "source": "live",
        }

    def ui_press(
        self,
        *,
        client: LiveClient | None = None,
        id: str,
        hold_ms: int | None = None,
        release: bool | None = None,
    ) -> dict:
        """Press (and optionally hold) one element; omit absent optional knobs."""
        params: dict[str, Any] = {"id": id}
        if hold_ms is not None:
            params["hold_ms"] = int(hold_ms)
        if release is not None:
            params["release"] = bool(release)
        result = self._request("ui_press", params, client)
        return {
            "pressed": str(result.get("pressed") or id),
            "held_ms": int(result.get("held_ms") or 0),
            "released": bool(result.get("released", False)),
            "source": "live",
        }

    # -- long work (P3) ----------------------------------------------------

    @staticmethod
    def _job(row: dict) -> dict:
        return {
            "id": row.get("id"),
            "kind": row.get("kind"),
            "status": row.get("status"),
            "progress": row.get("progress"),
            "elapsed_s": row.get("elapsed_s"),
            "message": row.get("message"),
        }

    def jobs_list(self, *, client: LiveClient | None = None) -> dict:
        result = self._request("jobs_list", {}, client)
        rows = [self._job(row) for row in self._rows(result, "jobs")]
        return {
            "count": int(result.get("count") or len(rows)),
            "jobs": rows,
            "source": "live",
        }

    def jobs_cancel(self, *, client: LiveClient | None = None, id: str) -> dict:
        result = self._request("jobs_cancel", {"id": id}, client)
        return {
            "cancelled": bool(result.get("cancelled", True)),
            "id": str(result.get("id") or id),
            "kind": str(result.get("kind") or ""),
            "source": "live",
        }
