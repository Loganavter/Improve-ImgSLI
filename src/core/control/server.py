"""The in-app control server: a ``QLocalServer`` on the runtime socket.

Started by ``src/__main__.py`` when ``IMGSLI_CONTROL=1`` and stopped on
``app.aboutToQuit``. Qt delivers ``QLocalServer``/``QLocalSocket`` readiness on
the GUI thread, so every handler runs where the widgets live — no threads, no
manual marshalling, actions are genuinely "as if a user clicked".

Wire protocol (newline-delimited JSON, one request per line)::

    {"id": <any>, "method": "<name>", "params": {...}}
    {"id": …, "ok": true,  "result": {...}}
    {"id": …, "ok": false, "error": "<msg>", "hint": "<next step>"}

Invariants this class enforces:
* ``start()`` never raises — ``False`` means the channel is unavailable and the
  app continues;
* a malformed line yields an error response and the connection survives;
* an unknown method yields an error + hint and the connection survives;
* a foreign-uid peer is closed before a byte is read (``SO_PEERCRED``);
* every handler is wrapped so a raise becomes an error envelope, never a crash;
* a handler that hangs inside a nested event loop (the app's own modal dialog)
  is answered **on the channel's own initiative** once it overruns
  ``MODAL_ACK_BUDGET_MS``; the handler's late result is then dropped, so one
  request never produces two frames (see ``_arm_early_answer``);
* the request being handled is recorded in ``inflight.json`` before the handler
  runs and the record is removed once the reply is sent (or, for a request the
  watchdog answered early, once the handler finally returns — the app is still
  busy with it) — a record left behind by a dead process is the only evidence a
  sibling has of *what* it died doing;
* the discovery pointer is written only after a successful ``listen()`` and is
  cleared (with the socket) on ``stop()``.

Refusals — every one is a **named** error envelope with a hint, never a silent
truncation, a hang, or a crash:

* **unknown method** — the name is not in ``handlers.METHODS`` (the hint lists
  the known methods and any close matches);
* **foreign uid** — the peer's ``SO_PEERCRED`` uid is not ours: the socket is
  aborted before a byte is read;
* **non-live ``press_keys``** — there is no focus widget / live window to
  receive keys, or a key/modifier name is not in the allowlist;
* **non-live ``ui_*``** — the element id never resolves while live (the hint
  lists close ids) or the element cannot take focus;
* **unknown / not-open surface** — ``capture_live`` with a ``what`` that is
  neither a known surface nor an *open* one (the two are distinguished);
* **oversized request** — a single request line above
  ``MAX_REQUEST_LINE_BYTES`` is answered with ``"request line too large"`` and
  the limit in the hint; the remainder of that line is discarded, so the
  connection survives and later lines are still served.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from . import discovery
from .discovery import MethodError

logger = logging.getLogger("ImproveImgSLI")

#: Logger whose records the live ``read_log`` ring captures.
APP_LOGGER_NAME = "ImproveImgSLI"

#: Owner-only mode for the socket file (matches the pointer).
_SOCKET_MODE = 0o600

#: Bounded size of the live log ring (records kept for ``read_log``).
_LOG_RING_CAPACITY = 2000

#: Hard cap on one request line (1 MiB). A larger line is refused by name
#: (``"request line too large"``) instead of being buffered/truncated silently.
MAX_REQUEST_LINE_BYTES = 1024 * 1024

#: Sanity cap on one serialized reply (8 MiB). A bigger (or unserialisable)
#: result is reported as an error frame, never emitted as a broken frame.
MAX_REPLY_BYTES = 8 * 1024 * 1024

#: How long a handler may run before the channel answers on its own behalf
#: (milliseconds). A handler that opens one of the app's modal dialogs
#: (``QFileDialog.getOpenFileName`` behind ``platform.open_project``, reached by
#: ``ctrl+shift+o`` through ``press_keys``/``run_action``/``ui_click``) is parked
#: inside that dialog's nested event loop until a human closes it, so the reply
#: would otherwise be written minutes later and the client would report
#: "sent, no reply" for a call that had already worked (and retry it).
#:
#: Chosen well above the slowest honest verb (a big capture / layout dump) and
#: well below the MCP client's 5 s request timeout, with room for the
#: round trip. Qt *does* deliver timers inside a nested modal loop, which is
#: what makes the early answer possible without a second thread — the transport
#: stays GUI-thread-only on purpose (see the module docstring).
MODAL_ACK_BUDGET_MS = 2000

#: Name of the in-flight request note, written next to the pointer. It is
#: written *before* a handler runs and removed once the reply is sent (for a
#: request the ack watchdog answered early: once its handler returns), so a note
#: that outlives the process is where the app died — the only trace a sibling
#: process can read after a segfault (no teardown, no reply). The MCP client
#: mirrors this name (`mcp-server/app/live.py`, stdlib-only, cannot import here).
INFLIGHT_NOTE_NAME = "inflight.json"

#: Cap on the redacted params digest kept in the note.
_PARAM_SUMMARY_LIMIT = 400

#: Per-value cap inside the digest.
_PARAM_VALUE_LIMIT = 48

#: Parameter NAMES whose value is never written down. ``run_action`` forwards
#: free-form params, so a token can sit in the request that kills the app.
_SECRET_KEY_RE = re.compile(
    r"(?i)(api[_-]?key|token|secret|passw|credential|authori[sz]|cookie|bearer|private[_-]?key)"
)

#: Values that *look* like a credential, whatever their parameter is called.
_SECRET_VALUE_RE = re.compile(
    r"(?i)^(sk-|pk-|ghp_|gho_|ghs_|github_pat_|xox[abp]-|bearer[ =:]|ey[A-Za-z0-9_-]{8,}\.)"
)


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

    Identifies the request after the fact without echoing what it carried:
    secret-named parameters become ``<redacted>``, credential-shaped values are
    masked wherever they appear, strings are truncated, and containers are
    reduced to their shape. ``mcp-server/app/live.py`` carries the same rule for
    the request *it* sent (it cannot import this module — stdlib only).
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


def encode_reply(payload: dict[str, Any]) -> bytes | None:
    """Serialize one reply into a newline-terminated frame, or ``None``.

    ``None`` means the payload cannot be framed — either it is not
    JSON-serialisable (e.g. a circular structure, which ``json.dumps`` raises
    on) or it exceeds ``MAX_REPLY_BYTES``. The caller then sends a named error
    frame instead of writing a broken/truncated frame that would desync the
    client's line reader.
    """
    try:
        blob = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    except Exception:
        return None
    if len(blob) > MAX_REPLY_BYTES:
        return None
    return blob + b"\n"


def _reply_error_frame(request_id: Any) -> bytes:
    """The fallback frame written when ``encode_reply`` refuses a payload."""
    payload = {
        "id": request_id,
        "ok": False,
        "error": "reply could not be framed",
        "hint": (
            f"the result was not JSON-serialisable or exceeded {MAX_REPLY_BYTES} "
            "bytes; check the app log via read_log"
        ),
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"


def _active_modal_widget() -> Any:
    """The modal widget blocking the app right now, or ``None``.

    Measured, never assumed: it is only ever reported as a *hint* on an early
    answer, because a native file dialog (the desktop portal on Wayland/Flatpak)
    is not a ``QWidget`` at all — ``None`` there means "no Qt modal widget",
    not "nothing is open". Imported lazily: the transport needs QtCore only.
    """
    try:
        from PySide6.QtWidgets import QApplication

        return QApplication.activeModalWidget()
    except Exception:
        return None


class LogRing(logging.Handler):
    """Bounded in-process capture of the app logger.

    ``log.txt`` is truncated by ``setup_logging`` on every start, so it cannot
    answer "what happened in the *running* process". This handler keeps the
    newest records in memory instead; the server attaches it to the app logger
    (``APP_LOGGER_NAME``) on start and detaches on stop.
    """

    def __init__(self, capacity: int = _LOG_RING_CAPACITY) -> None:
        super().__init__(level=logging.DEBUG)
        self._entries: deque[tuple[str, str]] = deque(maxlen=capacity)
        self.setFormatter(
            logging.Formatter("%(asctime)s - [%(levelname)s] - %(message)s")
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._entries.append((record.levelname, self.format(record)))
        except Exception:  # never let logging kill the app
            pass

    def entries(self) -> list[tuple[str, str]]:
        return list(self._entries)


class ControlServer:
    """Local control channel bound to a running ``MainWindow``.

    ``window`` is duck-typed (``.store`` plus optional live seams such as
    ``app_context.apply_theme_to_app``); ``app`` is the live ``QApplication``
    (used for the version, active window, and theme application).
    """

    def __init__(
        self,
        *,
        window: Any,
        app: Any,
        runtime_dir: Path | str | None = None,
        peer_checker: Callable[[int], bool] | None = None,
        log_ring: LogRing | None = None,
    ) -> None:
        self._window = window
        self._app = app
        self._runtime_dir = Path(runtime_dir) if runtime_dir else None
        # Injected in tests so uid refusal is proven without faking a real uid.
        self._peer_checker = peer_checker if peer_checker is not None else discovery.peer_uid_ok
        self._log_ring = log_ring
        self._server: QLocalServer | None = None
        self._handlers: ControlHandlers | None = None
        self._clients: dict[QLocalSocket, bytes] = {}
        # Clients whose current (oversized) line is being swallowed up to the
        # next newline — the named error was already sent for that line.
        self._discarding: set[QLocalSocket] = set()
        self._path: Path | None = None
        self._note_path: Path | None = None
        self._running = False
        #: How long a handler may run before the channel answers on its behalf
        #: (see ``MODAL_ACK_BUDGET_MS``). Tests shorten it.
        self._ack_budget_ms = MODAL_ACK_BUDGET_MS
        #: Bumped per recorded request so a late finisher cannot erase a newer
        #: request's in-flight note (see ``_note_inflight``/``_clear_inflight``).
        self._note_token = 0

    # -- state -------------------------------------------------------------

    @property
    def path(self) -> Path | None:
        return self._path

    def is_running(self) -> bool:
        return bool(
            self._running
            and self._server is not None
            and self._server.isListening()
        )

    def _version(self) -> str:
        try:
            return str(self._app.applicationVersion() or "") if self._app else ""
        except Exception:
            return ""

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> bool:
        """Bind the socket + publish the pointer; ``False`` on any failure."""
        if self.is_running():
            return True
        try:
            directory = self._runtime_dir or discovery.runtime_dir()
        except Exception as exc:
            logger.warning("control channel: no usable runtime dir: %s", exc)
            return False

        path = discovery.socket_path(directory)
        try:
            if discovery.stale_pointer_alive():
                logger.warning(
                    "control channel: another live app owns %s — not starting",
                    directory,
                )
                return False
            self._clear_leftovers(path)
            server = QLocalServer()
            server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
            server.newConnection.connect(self._on_new_connection)
            if not server.listen(str(path)):
                logger.warning(
                    "control channel: listen failed on %s (%s)",
                    path,
                    server.errorString(),
                )
                server.deleteLater()
                return False
            try:
                os.chmod(path, _SOCKET_MODE)
            except OSError:
                pass
        except Exception as exc:
            logger.warning("control channel: could not start: %s", exc, exc_info=True)
            return False

        self._server = server
        self._path = path
        self._running = True
        # A leftover note belongs to a previous, dead process: clear it so this
        # instance's death report can never quote someone else's last request.
        self._note_path = directory / INFLIGHT_NOTE_NAME
        self._clear_inflight()
        ring = self._log_ring or LogRing()
        self._log_ring = ring
        logging.getLogger(APP_LOGGER_NAME).addHandler(ring)
        # Deferred import: handlers imports this module's primitives at load.
        from .handlers import ControlHandlers

        self._handlers = ControlHandlers(
            window=self._window,
            app=self._app,
            artifacts_dir=discovery.artifacts_dir(),
            log_ring=ring,
        )
        try:
            discovery.write_pointer(
                pid=os.getpid(), socket=path, version=self._version()
            )
        except Exception as exc:  # serve anyway; discovery is best-effort
            logger.warning("control channel: pointer write failed: %s", exc)
        logger.info("control channel listening: %s (pid %s)", path, os.getpid())
        return True

    def stop(self) -> None:
        """Tear the channel down: close clients, remove socket + pointer."""
        self._running = False
        for socket in list(self._clients):
            try:
                socket.disconnectFromServer()
                socket.close()
            except Exception:
                pass
        self._clients.clear()
        self._discarding.clear()
        if self._server is not None:
            try:
                self._server.close()
            except Exception:
                pass
            self._server = None
        ring = self._log_ring
        self._log_ring = None
        if ring is not None:
            try:
                logging.getLogger(APP_LOGGER_NAME).removeHandler(ring)
            except Exception:
                pass
        try:
            discovery.clear_pointer()
        except Exception:
            pass
        # A clean stop is not a death: nothing should be left to explain.
        self._clear_inflight()
        self._note_path = None
        if self._path is not None:
            try:
                self._path.unlink(missing_ok=True)
            except OSError:
                pass
        self._path = None

    @staticmethod
    def _clear_leftovers(path: Path) -> None:
        """Remove a crashed app's socket file so ``listen()`` can bind."""
        try:
            QLocalServer.removeServer(str(path))
        except Exception:
            pass
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    # -- connections -------------------------------------------------------

    def _on_new_connection(self) -> None:
        if self._server is None:
            return
        socket = self._server.nextPendingConnection()
        if socket is None:
            return
        if not self._peer_is_self(socket):
            logger.warning("control channel: refused a foreign-uid connection")
            try:
                socket.abort()
            except Exception:
                pass
            return
        self._clients[socket] = b""
        socket.readyRead.connect(lambda s=socket: self._on_ready_read(s))
        socket.disconnected.connect(lambda s=socket: self._drop_client(s))
        try:
            socket.errorOccurred.connect(lambda _err, s=socket: self._drop_client(s))
        except Exception:
            pass

    def _peer_is_self(self, socket: QLocalSocket) -> bool:
        try:
            descriptor = int(socket.socketDescriptor())
        except Exception:
            return False
        try:
            return bool(self._peer_checker(descriptor))
        except Exception:
            return False

    def _on_ready_read(self, socket: QLocalSocket) -> None:
        buffer = self._clients.get(socket)
        if buffer is None:
            return
        try:
            chunk = socket.readAll()
            buffer += chunk.data() if chunk is not None else b""
        except Exception:
            self._drop_client(socket)
            return
        # We already refused the current (oversized) line: swallow bytes until
        # its terminating newline so its tail is not mis-parsed as a new line.
        if socket in self._discarding:
            if b"\n" not in buffer:
                self._clients[socket] = b""
                return
            _rejected, buffer = buffer.split(b"\n", 1)
            self._discarding.discard(socket)
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            if len(line) > MAX_REQUEST_LINE_BYTES:
                self._refuse_oversized_line(socket)
                continue
            self._handle_line(socket, line)
        if len(buffer) > MAX_REQUEST_LINE_BYTES:
            # One line still streaming in and already past the cap — refuse it
            # now (never buffer unbounded) and swallow the rest of that line.
            self._refuse_oversized_line(socket)
            self._discarding.add(socket)
            buffer = b""
        self._clients[socket] = buffer

    def _refuse_oversized_line(self, socket: QLocalSocket) -> None:
        """Named refusal for a request line over ``MAX_REQUEST_LINE_BYTES``."""
        self._send(
            socket,
            {
                "id": None,
                "ok": False,
                "error": "request line too large",
                "hint": (
                    f"send at most {MAX_REQUEST_LINE_BYTES} bytes per line "
                    "(one JSON object per line)"
                ),
            },
        )

    def _drop_client(self, socket: QLocalSocket) -> None:
        self._discarding.discard(socket)
        if self._clients.pop(socket, None) is None:
            return
        try:
            socket.close()
        except Exception:
            pass
        try:
            socket.deleteLater()
        except Exception:
            pass

    # -- request handling --------------------------------------------------

    def _note_inflight(
        self, *, request_id: Any, method: str, params: dict[str, Any]
    ) -> int | None:
        """Record the request about to run, atomically, next to the pointer.

        Written to a sibling temp file then ``os.replace``-d so a reader never
        sees a half-written note. Best-effort: a read-only runtime dir must not
        stop the request from running.

        Returns this request's token. The note is one slot, and a handler parked
        in a modal loop still *re-enters* this method — the nested loop serves a
        **new** connection's first line (Qt guards ``readyRead`` against
        re-entry per socket, not per server). A late finisher must therefore not
        erase a newer request's record: that record is the only evidence left if
        the app then dies in the newer call (``_clear_inflight`` takes the
        token).
        """
        if self._note_path is None:
            return None
        self._note_token += 1
        token = self._note_token
        payload = {
            "method": method,
            "summary": summarize_request_params(params),
            "request_id": request_id
            if isinstance(request_id, (int, float, str))
            else None,
            "pid": os.getpid(),
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        tmp = self._note_path.with_name(
            self._note_path.name + f".tmp.{os.getpid()}"
        )
        try:
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            os.chmod(tmp, _SOCKET_MODE)
            os.replace(tmp, self._note_path)
        except OSError:
            logger.debug("control channel: could not record the in-flight request")
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
        return token

    def _clear_inflight(self, token: int | None = None) -> None:
        """Drop the in-flight record: the app answered, or is shutting down.

        ``token`` (from :meth:`_note_inflight`) makes the clear conditional:
        a request that finishes after a nested one took the note over must leave
        that newer record alone — it may be all that explains a death.
        """
        if self._note_path is None:
            return
        if token is not None and token != self._note_token:
            return
        try:
            self._note_path.unlink(missing_ok=True)
        except OSError:
            pass

    def _reply(self, socket: QLocalSocket, payload: dict[str, Any]) -> None:
        """Send one reply, then clear the note (the app survived the request)."""
        self._send(socket, payload)
        self._clear_inflight()

    def _arm_early_answer(
        self, socket: QLocalSocket, request_id: Any, method: str
    ) -> tuple[QTimer, dict[str, bool]]:
        """Arm the watchdog that answers a handler parked inside a nested loop.

        The chord path is synchronous: ``press_keys ctrl+shift+o`` runs
        ``platform.open_project`` inline, which calls
        ``QFileDialog.getOpenFileName`` — a modal ``exec()``. Every handler reply
        is written *after* the handler returns, so the answer would sit inside
        the dialog until a human closed it and the client would time out on a
        call that had already worked. Qt delivers timers inside that nested
        loop, so the timer (not a thread) is what lets the channel answer.

        Returns the timer and the state the caller must consult: once
        ``state["answered"]`` is set, a frame is already on the wire and the
        late real result must be dropped (never a second frame for one id).

        The answer is ``ok: true`` with ``answered_early`` because the request
        *is* being carried out; reporting it as a failure would invite the retry
        that double-applies the edit. A handler that fails *before* the budget
        is unaudited by this: it returns (or raises) first and keeps its own
        full result / named error.
        """
        state = {"answered": False}

        def _overran() -> None:
            if state["answered"]:
                return
            state["answered"] = True
            modal = _active_modal_widget()
            # ``_send``, not ``_reply``: the in-flight note stays until the
            # handler returns, because the app is still busy with this request
            # and a crash in the dialog would otherwise leave no record of it.
            self._send(
                socket,
                {
                    "id": request_id,
                    "ok": True,
                    "result": {
                        "accepted": True,
                        "answered_early": True,
                        "still_running": True,
                        "modal_open": modal is not None,
                        "method": method,
                        "budget_ms": self._ack_budget_ms,
                    },
                },
            )
            logger.info(
                "control channel: %s still running after %s ms (%s) — answered "
                "early; its real result will be dropped",
                method,
                self._ack_budget_ms,
                "a Qt modal widget is open"
                if modal is not None
                else "no Qt modal widget",
            )

        timer = QTimer()
        timer.setSingleShot(True)
        timer.setInterval(self._ack_budget_ms)
        timer.timeout.connect(_overran)
        timer.start()
        return timer, state

    def _handle_line(self, socket: QLocalSocket, line: bytes) -> None:
        if not line.strip():
            return  # stray blank line — ignore, never an error
        try:
            request = json.loads(line.decode("utf-8"))
        except Exception:
            self._send(
                socket,
                {
                    "id": None,
                    "ok": False,
                    "error": "malformed request line",
                    "hint": 'send one JSON object per line, e.g. {"id":1,"method":"ping","params":{}}',
                },
            )
            return
        if not isinstance(request, dict):
            self._send(
                socket,
                {
                    "id": None,
                    "ok": False,
                    "error": "request must be a JSON object",
                    "hint": 'e.g. {"id":1,"method":"ping","params":{}}',
                },
            )
            return
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params")
        if not isinstance(params, dict):
            params = {}
        if not isinstance(method, str) or not method:
            self._send(
                socket,
                {
                    "id": request_id,
                    "ok": False,
                    "error": "request is missing a method",
                    "hint": "call get_capabilities for the method list",
                },
            )
            return
        if self._handlers is None:
            self._send(
                socket,
                {
                    "id": request_id,
                    "ok": False,
                    "error": "control handlers are not ready",
                    "hint": "retry after the app finishes starting",
                },
            )
            return
        # Record the request before it can die: a handler that takes the process
        # down (segfault, abort) never reaches the reply below, so this note is
        # what survives to explain the death to the MCP client.
        note = self._note_inflight(request_id=request_id, method=method, params=params)
        timer, answer = self._arm_early_answer(socket, request_id, method)
        try:
            try:
                result = self._handlers.handle(method, params)
            except MethodError as exc:
                if answer["answered"]:
                    self._report_late_failure(method, exc, note)
                    return
                self._reply(
                    socket,
                    {
                        "id": request_id,
                        "ok": False,
                        "error": exc.message,
                        "hint": exc.hint,
                    },
                )
                return
            except Exception as exc:
                if answer["answered"]:
                    self._report_late_failure(method, exc, note)
                    return
                logger.debug("control channel: handler %s failed", method, exc_info=True)
                self._reply(
                    socket,
                    {
                        "id": request_id,
                        "ok": False,
                        "error": f"{type(exc).__name__}: {exc}",
                        "hint": "unexpected failure; check the app log via read_log",
                    },
                )
                return
        finally:
            # No event is processed between the handler returning and the reply
            # below, so a stopped watchdog can never race that frame.
            timer.stop()
        if answer["answered"]:
            # Already answered while the handler was parked in a modal loop: the
            # one-frame-per-request rule wins over reporting the real result.
            self._clear_inflight(note)
            logger.debug(
                "control channel: %s returned after its early answer — result dropped",
                method,
            )
            return
        self._reply(socket, {"id": request_id, "ok": True, "result": result})

    def _report_late_failure(
        self, method: str, exc: BaseException, note: int | None
    ) -> None:
        """A handler that overran then failed: the client already has its frame.

        Nothing can be rewritten on the wire, so the failure goes to the log
        (``read_log`` serves it) instead of vanishing, and the in-flight note is
        cleared (only if this request still owns it) — the app is alive, it just
        cannot report this one.
        """
        logger.warning(
            "control channel: %s failed after it was answered early: %s: %s",
            method,
            type(exc).__name__,
            exc,
        )
        self._clear_inflight(note)

    def _send(self, socket: QLocalSocket, payload: dict[str, Any]) -> None:
        request_id = payload.get("id") if isinstance(payload, dict) else None
        frame = encode_reply(payload) if isinstance(payload, dict) else None
        if frame is None:
            frame = _reply_error_frame(request_id)
        try:
            socket.write(frame)
            socket.flush()
        except Exception:
            self._drop_client(socket)
