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
  A pointer whose pid is dead is stale, and a socket nobody listens on is "no
  live instance" — never a user-visible error.
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


class LiveUnavailable(Exception):
    """No live instance answered: socket missing/stale, refused, or closed.

    The caller falls back to Phase 1; this never reaches the user as an error.
    """

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


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


def _pointer_socket(directory: Path) -> tuple[Path | None, bool]:
    """``(socket, stale)`` for a control dir with an ``instance.json`` pointer.

    ``socket`` is the pointer's ``socket`` field, falling back to the sibling
    ``control.sock``. ``stale`` is true when the pointer names a dead pid — a
    stale pointer must be reported as "no live instance", never trusted.
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
    pid = data.get("pid")
    if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0 and not pid_alive(pid):
        return None, True
    field = data.get("socket")
    if isinstance(field, str) and field.strip():
        return Path(field.strip()).expanduser(), False
    return directory / CONTROL_SOCKET_NAME, False


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
            raise LiveUnavailable(f"no control socket at {self.socket_path}")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(self.timeout)
            sock.connect(str(self.socket_path))
        except OSError as exc:
            sock.close()
            raise LiveUnavailable(f"cannot connect to the control socket: {exc}")
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
                    raise LiveUnavailable("timed out waiting for the control socket")
                sock.settimeout(remaining)
                try:
                    chunk = sock.recv(65536)
                except socket.timeout:
                    raise LiveUnavailable("timed out waiting for the control socket")
                except OSError as exc:
                    raise LiveUnavailable(f"control socket read failed: {exc}")
                if not chunk:
                    raise LiveUnavailable("the control socket was closed by the app")
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
                raise LiveUnavailable("no response with our request id from the control socket")

    def call(self, method: str, params: dict | None = None) -> dict:
        """Send one request, return its ``result`` object.

        Raises ``LiveUnavailable`` (transport) or ``LiveError`` (app-reported
        failure with the app's own message and hint).
        """
        self._counter += 1
        request_id = self._counter
        payload = json.dumps(
            {"id": request_id, "method": method, "params": params or {}},
            ensure_ascii=False,
        )
        try:
            sock = self._connect()
            sock.sendall(payload.encode("utf-8") + b"\n")
            message = self._read_message(sock, request_id)
        except LiveUnavailable:
            self.close()
            raise
        except OSError as exc:
            self.close()
            raise LiveUnavailable(f"control socket {self.socket_path} failed: {exc}")
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

    def _request(self, method: str, params: dict, client: LiveClient | None) -> dict:
        active = client or self.client_if_alive()
        if active is None:
            raise LiveUnavailable("no live instance is attached")
        return active.call(method, params)

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

    def open_folder(self, *, client: LiveClient | None = None, path: str) -> dict:
        result = self._request("open_folder", {"path": path}, client)
        return {
            "ran": bool(result.get("ran", True)),
            "path": str(result.get("path") or path),
            "routed": bool(result.get("routed", True)),
            "live": True,
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

    def press_keys(self, *, client: LiveClient | None = None, keys: str) -> dict:
        """Inject keyboard input (live-only; there is no headless analogue)."""
        result = self._request("press_keys", {"keys": keys}, client)
        pressed = [str(item) for item in result.get("pressed") or []]
        return {
            "pressed": pressed,
            "count": int(result.get("count", len(pressed))),
            "target": str(result.get("target") or ""),
            "source": "live",
        }
