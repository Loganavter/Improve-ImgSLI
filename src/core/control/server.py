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
* the discovery pointer is written only after a successful ``listen()`` and is
  cleared (with the socket) on ``stop()``.
"""

from __future__ import annotations

import json
import logging
import os
from collections import deque
from pathlib import Path
from typing import Any, Callable

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
        self._path: Path | None = None
        self._running = False

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
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            self._handle_line(socket, line)
        self._clients[socket] = buffer

    def _drop_client(self, socket: QLocalSocket) -> None:
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
        try:
            result = self._handlers.handle(method, params)
        except MethodError as exc:
            self._send(
                socket,
                {"id": request_id, "ok": False, "error": exc.message, "hint": exc.hint},
            )
            return
        except Exception as exc:
            logger.debug("control channel: handler %s failed", method, exc_info=True)
            self._send(
                socket,
                {
                    "id": request_id,
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "hint": "unexpected failure; check the app log via read_log",
                },
            )
            return
        self._send(socket, {"id": request_id, "ok": True, "result": result})

    def _send(self, socket: QLocalSocket, payload: dict[str, Any]) -> None:
        try:
            blob = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            socket.write(blob + b"\n")
            socket.flush()
        except Exception:
            self._drop_client(socket)
