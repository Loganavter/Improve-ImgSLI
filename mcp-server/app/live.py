"""Client + adapter for the app's live control socket (Phase 2 channel).

Phase 1 (``backend.py``) can only boot throwaway headless apps; this module
attaches to an *already running* instance over the frozen in-app control
protocol and proxies the MCP tool surface onto it:

- **Transport** — a Qt QLocalServer unix socket in the app. Newline-delimited
  JSON: one request ``{"id", "method", "params"}`` per line, one response
  ``{"id", "ok": true, "result"}`` / ``{"id", "ok": false, "error", "hint"}``.
- **Discovery** — ``IMGSLI_MCP_CONTROL_SOCKET`` (explicit socket path) →
  ``IMGSLI_CONTROL_DIR`` (explicit dir) → ``$XDG_RUNTIME_DIR`` when set and
  writable → ``<app data dir>/run``. The socket is ``control.sock`` and a
  pointer file ``instance.json`` holds ``{pid, socket, started, version}``.
  A pointer is stale only when its socket is unusable: the pid is a hint, not
  the verdict (Flatpak apps live in their own PID namespace), and a socket
  nobody listens on is "no live instance" — never a user-visible error.
- **Degrading cleanly** — the app refuses connections from another uid (its own
  SO_PEERCRED check, not ours) and may close the socket at any time; every
  failure surfaces as ``LiveUnavailable`` so the caller falls back to Phase 1.

Stdlib only, like the rest of ``mcp-server/app``.
"""

from __future__ import annotations

import json
import os
import socket
import stat
import sys
import time
from pathlib import Path
from typing import Any, Mapping

from .process_policy import pid_alive

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

#: Explicit overrides, highest priority first.
SOCKET_OVERRIDE_ENV = "IMGSLI_MCP_CONTROL_SOCKET"
CONTROL_DIR_ENV = "IMGSLI_CONTROL_DIR"

#: Cap on ignored lines while waiting for our own response id.
_MAX_SKIPPED_LINES = 100

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
    expiry specifically (the reads' one retry is scoped to timeouts).
    """

    def __init__(
        self,
        message: str,
        hint: str | None = None,
        *,
        sent: bool = False,
        timeout: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.sent = bool(sent)
        self.timeout = bool(timeout)


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


def _app_data_dir(env: Mapping[str, str]) -> Path:
    """Per-OS app data dir — mirrors ``backend.app_data_dir`` for explicit envs."""
    if sys.platform.startswith("linux"):
        base = env.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:  # pragma: no cover - Windows
        base = env.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "ImproveImgSLI"


def _runtime_candidates(env: Mapping[str, str]) -> list[Path]:
    """Control dirs to probe, in the app's own priority order."""
    candidates: list[Path] = []
    runtime = (env.get("XDG_RUNTIME_DIR") or "").strip()
    if runtime and os.path.isdir(runtime) and os.access(runtime, os.W_OK):
        candidates.append(Path(runtime))
    candidates.append(_app_data_dir(env) / "run")
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


def _pointer_socket(directory: Path) -> tuple[Path | None, bool]:
    """``(socket, stale)`` for a control dir with an ``instance.json`` pointer.

    ``socket`` is the pointer's ``socket`` field, falling back to the sibling
    ``control.sock``. ``stale`` means "nothing usable here": the pointer is
    reported as "no live instance" and must not be trusted.

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
    try:
        data = json.loads(pointer.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, False
    if not isinstance(data, dict):
        return None, False
    field = data.get("socket")
    if isinstance(field, str) and field.strip():
        candidate = Path(field.strip()).expanduser()
    else:
        candidate = directory / CONTROL_SOCKET_NAME
    pid = data.get("pid")
    verifiable_pid = isinstance(pid, int) and not isinstance(pid, bool) and pid > 0
    if verifiable_pid and not pid_alive(pid) and not _socket_answers(candidate):
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
    then ``$XDG_RUNTIME_DIR`` (when set and writable) and the app-data ``run``
    dir. An override that points at nothing plausible yields ``None`` — the
    caller treats that as "no live instance", not an error.
    """
    source = dict(os.environ) if env is None else env

    explicit = (source.get(SOCKET_OVERRIDE_ENV) or "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        return path if _is_socket(path) else None

    override_dir = (source.get(CONTROL_DIR_ENV) or "").strip()
    if override_dir:
        return _socket_in_dir(Path(override_dir).expanduser())

    for directory in _runtime_candidates(source):
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

    def __init__(self, socket_path: Path | str, *, timeout: float = DEFAULT_TIMEOUT_S) -> None:
        self.socket_path = Path(socket_path)
        self.timeout = float(timeout)
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
        except LiveUnavailable:
            self.close()
            raise
        except OSError as exc:
            self.close()
            raise LiveUnavailable(
                f"{SENT_NO_REPLY}: control socket {self.socket_path} failed: {exc}", sent=True
            )
        if message.get("ok") is not True:
            raise LiveError(str(message.get("error") or f"{method} failed"), _hint(message))
        result = message.get("result")
        if result is None:
            return {}
        if not isinstance(result, dict):
            raise LiveError(f"{method} returned a non-object result", "report an app-side bug")
        return result

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
            candidate = LiveClient(path, timeout=self.timeout)
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
            "read_log",
            "query_trace",
            "dump_ui_layout",
            "list_surfaces",
            "ui_elements",
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
        self, *, client: LiveClient | None = None, action_id: str, tab: str | None = None
    ) -> dict:
        params: dict[str, Any] = {"action_id": action_id}
        if tab:
            params["tab"] = tab
        result = self._request("run_action", params, client)
        return {
            "ran": bool(result.get("ran", True)),
            "action_id": result.get("action_id", action_id),
            "tab": result.get("tab", tab),
            "live": True,
            "source": "live",
        }

    def open_folder(
        self, *, client: LiveClient | None = None, path: str, tab: str | None = None
    ) -> dict:
        params: dict[str, Any] = {"path": path}
        if tab:
            params["tab"] = tab
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

    def capture_surface(
        self,
        *,
        client: LiveClient | None = None,
        surface: str,
        theme: str | None = None,
        out: str | None = None,
    ) -> dict:
        """Proxy ``capture_live`` and normalise to the Phase-1 capture shape.

        An empty ``path`` means the live app answered without a file (e.g. it
        returned inline data this adapter does not save yet) — honest, not fake.
        """
        params: dict[str, Any] = {"what": surface}
        if theme:
            params["theme"] = theme
        if out:
            params["out"] = out
        result = self._request("capture_live", params, client)
        return {
            "surface": str(result.get("surface") or surface),
            "path": str(result.get("path") or ""),
            "theme": str(result.get("theme") or theme or "dark"),
            "live": True,
            "source": "live",
        }

    def press_keys(
        self, *, client: LiveClient | None = None, keys: str, target: str | None = None
    ) -> dict:
        """Inject keyboard input (live-only; there is no headless analogue).

        ``target`` names an element id (``ui_elements``) so the keys reach a
        widget the window focus chain never gives them -- a canvas, whose
        zoom/pan keys are its own. Without it, the running app's focus widget
        receives them (the historical behaviour).
        """
        params: dict[str, Any] = {"keys": keys}
        if target:
            params["target"] = target
        result = self._request("press_keys", params, client)
        pressed = [str(item) for item in result.get("pressed") or []]
        return {
            "pressed": pressed,
            "count": int(result.get("count", len(pressed))),
            "target": str(result.get("target") or ""),
            "source": "live",
        }

    # -- element targeting (live-only) -------------------------------------

    @staticmethod
    def _element(row: dict) -> dict:
        """One inventory row, normalised to the declared element shape."""
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
        }

    def ui_elements(
        self,
        *,
        client: LiveClient | None = None,
        scope: str | None = None,
        include_disabled: bool | None = None,
    ) -> dict:
        params: dict[str, Any] = {}
        if scope:
            params["scope"] = scope
        if include_disabled:
            params["include_disabled"] = bool(include_disabled)
        result = self._request("ui_elements", params, client)
        rows = [self._element(row) for row in self._rows(result, "elements")]
        return {
            "count": int(result.get("count") or len(rows)),
            "window_count": int(result.get("window_count") or 0),
            "elements": rows,
            "source": "live",
        }

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
