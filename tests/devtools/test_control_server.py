"""``core.control.server`` + ``core.control.handlers`` over a live app object.

The socket tests drive a real ``QLocalServer`` through a real ``QLocalSocket``
in-process (Qt delivers on the GUI thread — no threads needed). The handler
tests run against a real ``Store`` and a fake ``ActionRegistry``, proving
``run_action``/``open_tab`` call the registered runners rather than reporting
success blindly.

Falsification (written first, red against a naive implementation):
* ``unknown method must not kill the connection``
* ``malformed line must not kill the connection``
* ``foreign uid refused``
"""

from __future__ import annotations

import json
import logging
import os
import time
import types

import pytest

from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtWidgets import QApplication, QWidget

from core.actions.types import ActionDescriptor
from core.control import capture, discovery
from core.control.handlers import ControlHandlers, MethodError
from core.control.server import ControlServer, LogRing
from core.store import Store
from ui.actions.registry import ActionRegistry
from core.log_names import APP_LOGGER_NAME

_CONNECTED = QLocalSocket.LocalSocketState.ConnectedState

#: capture_live needs a real (and NOT the user's) display — a private Xvfb.
_DISPLAY = os.environ.get("DISPLAY", "")
_CAPTURE_READY = (
    os.environ.get("QT_QPA_PLATFORM") != "offscreen"
    and _DISPLAY.startswith(":")
    and _DISPLAY.split(".", 1)[0] != ":0"
)


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pump(app: QApplication, seconds: float, until=None) -> bool:
    """Spin the Qt event loop until *until* holds (or timeout) — no threads."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        if until is not None and until():
            return True
        time.sleep(0.005)
    app.processEvents()
    return bool(until()) if until is not None else False


class _Client:
    """Minimal newline-JSON client over a real QLocalSocket."""

    def __init__(self, app: QApplication, path) -> None:
        self.app = app
        self.buffer = b""
        #: When the first complete frame reached *this* end of the socket —
        #: the only way to prove a reply was written while the app was still
        #: inside a handler (see the modal-dialog test below).
        self.first_line_at: float | None = None
        self.socket = QLocalSocket()
        self.socket.readyRead.connect(self._read)
        self.socket.connectToServer(str(path))
        _pump(app, 3.0, lambda: self.socket.state() == _CONNECTED)

    def _read(self) -> None:
        chunk = self.socket.readAll()
        self.buffer += chunk.data() if chunk is not None else b""
        if self.first_line_at is None and b"\n" in self.buffer:
            self.first_line_at = time.time()

    def send(self, payload: dict) -> None:
        self.send_raw(json.dumps(payload).encode("utf-8") + b"\n")

    def send_raw(self, data: bytes) -> None:
        self.socket.write(data)
        self.socket.flush()

    def wait_line(self, seconds: float = 3.0):
        if not _pump(self.app, seconds, lambda: b"\n" in self.buffer):
            return None
        line, self.buffer = self.buffer.split(b"\n", 1)
        return json.loads(line)

    def close(self) -> None:
        try:
            self.socket.close()
        except Exception:
            pass


def _store_window() -> types.SimpleNamespace:
    return types.SimpleNamespace(store=Store())


def _registry(*actions: ActionDescriptor) -> ActionRegistry:
    registry = ActionRegistry()
    for action in actions:
        registry.register(action)
    return registry


def _descriptor(action_id: str, run=None, **kwargs) -> ActionDescriptor:
    return ActionDescriptor(
        action_id=action_id,
        label_key=f"action.{action_id}",
        description_key=f"action.{action_id}_desc",
        run=run,
        **kwargs,
    )


def _handlers(window, registry, tmp_path, *, app=None, ring=None) -> ControlHandlers:
    return ControlHandlers(
        window=window,
        app=app,
        artifacts_dir=tmp_path / "artifacts",
        log_ring=ring,
        registry_provider=lambda: registry,
    )


# -- socket transport ------------------------------------------------------


def test_round_trip_ping_capabilities_and_stop_cleanup(tmp_path, monkeypatch):
    monkeypatch.setenv("IMGSLI_CONTROL_DIR", str(tmp_path / "ctrl"))
    app = _qapp()
    server = ControlServer(window=_store_window(), app=app)
    try:
        assert server.start() is True
        assert server.is_running() is True
        assert server.path is not None and server.path.exists()
        assert discovery.read_pointer() is not None

        client = _Client(app, server.path)
        try:
            assert client.socket.state() == _CONNECTED
            client.send({"id": 1, "method": "ping", "params": {}})
            ping = client.wait_line()
            assert ping["ok"] is True
            assert ping["result"]["pong"] is True
            assert ping["result"]["pid"] == os.getpid()
            # A fast call keeps its own result: the ack watchdog only speaks for
            # a handler that is still running (see the modal-dialog test).
            assert "answered_early" not in ping["result"]

            client.send({"id": 2, "method": "get_capabilities", "params": {}})
            caps = client.wait_line()
            assert caps["ok"] is True
            assert "ping" in caps["result"]["methods"]
            assert caps["result"]["live_actions"] is True
            assert caps["result"]["live_keys"] is True
            assert "press_keys" in caps["result"]["methods"]
            assert caps["result"]["subscribe"] is False
        finally:
            client.close()
    finally:
        path = server.path
        pointer = discovery.pointer_path()
        server.stop()

    assert server.is_running() is False
    assert path is not None and not path.exists(), "socket file removed on stop"
    assert not pointer.exists(), "pointer removed on stop"


def test_unknown_method_is_an_error_and_the_connection_survives(tmp_path, monkeypatch):
    monkeypatch.setenv("IMGSLI_CONTROL_DIR", str(tmp_path / "ctrl"))
    app = _qapp()
    server = ControlServer(window=_store_window(), app=app)
    assert server.start() is True
    client = _Client(app, server.path)
    try:
        client.send({"id": 10, "method": "no_such_method", "params": {}})
        response = client.wait_line()
        assert response == {
            "id": 10,
            "ok": False,
            "error": "unknown method 'no_such_method'",
            "hint": response["hint"],
        }
        assert "known methods" in response["hint"]

        # The connection must still answer the next request.
        client.send({"id": 11, "method": "ping", "params": {}})
        assert client.wait_line()["ok"] is True
    finally:
        client.close()
        server.stop()


def test_malformed_line_is_an_error_and_the_connection_survives(tmp_path, monkeypatch):
    monkeypatch.setenv("IMGSLI_CONTROL_DIR", str(tmp_path / "ctrl"))
    app = _qapp()
    server = ControlServer(window=_store_window(), app=app)
    assert server.start() is True
    client = _Client(app, server.path)
    try:
        client.send_raw(b"this is not json\n")
        response = client.wait_line()
        assert response["ok"] is False
        assert response["error"] == "malformed request line"

        client.send({"id": 12, "method": "ping", "params": {}})
        assert client.wait_line()["ok"] is True
    finally:
        client.close()
        server.stop()


def test_oversized_request_line_is_refused_by_name_and_the_connection_survives(
    tmp_path, monkeypatch
):
    from core.control.server import MAX_REQUEST_LINE_BYTES

    monkeypatch.setenv("IMGSLI_CONTROL_DIR", str(tmp_path / "ctrl"))
    app = _qapp()
    server = ControlServer(window=_store_window(), app=app)
    assert server.start() is True
    client = _Client(app, server.path)
    try:
        oversized = b"x" * (MAX_REQUEST_LINE_BYTES + 64)
        client.send_raw(oversized + b"\n")
        response = client.wait_line(seconds=5.0)
        assert response is not None, "an oversized line is answered, not dropped"
        assert response["ok"] is False
        assert response["error"] == "request line too large"
        assert str(MAX_REQUEST_LINE_BYTES) in response["hint"]

        # The refused line is swallowed whole — the next request is still served.
        client.send({"id": 20, "method": "ping", "params": {}})
        assert client.wait_line()["ok"] is True
    finally:
        client.close()
        server.stop()


def test_inflight_note_survives_a_handler_crash_and_is_cleared_by_a_reply(
    tmp_path, monkeypatch
):
    """The request being handled must outlive a crash — that note *is* the evidence.

    A segfault never runs teardown and never writes a reply, so the only trace a
    sibling process can read is the note written before the handler ran. A
    request that *is* answered must clear it, or the next "no live instance"
    answer would quote an old request.
    """
    from core.control.server import INFLIGHT_NOTE_NAME

    monkeypatch.setenv("IMGSLI_CONTROL_DIR", str(tmp_path / "ctrl"))
    app = _qapp()
    server = ControlServer(window=_store_window(), app=app)
    assert server.start() is True
    note = tmp_path / "ctrl" / INFLIGHT_NOTE_NAME

    class _Crash(BaseException):
        """A crash analogue: ``_handle_line`` catches ``Exception`` only."""

    class _CrashingHandlers:
        def handle(self, method, params):
            if method == "press_keys":
                raise _Crash("the process is going down")
            return {"pong": True, "pid": os.getpid()}

    class _RecordingSocket:
        """``_send`` only needs ``write`` + ``flush``."""

        def __init__(self):
            self.written = b""

        def write(self, data):
            self.written += bytes(data)

        def flush(self):
            pass

    socket_double = _RecordingSocket()
    try:
        server._handlers = _CrashingHandlers()
        assert not note.exists()
        line = json.dumps(
            {
                "id": 1,
                "method": "press_keys",
                "params": {"keys": "ctrl+p", "api_key": "sk-or-v1-di0dbeef"},
            }
        ).encode("utf-8")
        with pytest.raises(_Crash):
            server._handle_line(socket_double, line)
        # The handler died without a reply: the note names the request ...
        assert note.is_file(), "a crash must leave the in-flight record behind"
        payload = json.loads(note.read_text(encoding="utf-8"))
        assert payload["method"] == "press_keys"
        assert payload["summary"] == "keys='ctrl+p', api_key=<redacted>"
        assert payload["pid"] == os.getpid()
        assert payload["at"]
        assert "di0dbeef" not in note.read_text(encoding="utf-8")
        assert socket_double.written == b"", "no reply was written"
        # ... and an answered request clears it again.
        server._handle_line(socket_double, b'{"id": 2, "method": "ping", "params": {}}')
        assert not note.exists(), "a reply means the app survived that request"
        assert json.loads(socket_double.written.decode("utf-8"))["ok"] is True
    finally:
        server.stop()


def test_a_chord_that_opens_a_modal_dialog_is_answered_inside_its_loop(
    tmp_path, monkeypatch
):
    """A call that opens the app's modal dialog must still answer its request.

    ``press_keys ctrl+shift+o`` runs ``platform.open_project`` inline, and that
    action calls ``QFileDialog.getOpenFileName`` — a modal event loop. The reply
    used to be written only *after* the handler returned, so it stayed inside
    the dialog for as long as the dialog stayed on screen: the client reported
    "sent, no reply" (its 5 s timeout) for a chord that had already opened the
    window, and a retry opened a second one.

    Red before the ack watchdog: no timer existed, so the first frame a client
    could read arrived only after ``exec()`` returned — the assertion that fails
    is ``client.first_line_at < handlers.returned_at`` (the frame that arrives
    is the handler's own result, 700 ms late).
    """
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setenv("IMGSLI_CONTROL_DIR", str(tmp_path / "ctrl"))
    app = _qapp()
    server = ControlServer(window=_store_window(), app=app)
    assert server.start() is True
    # The production budget is seconds; shorten it so the test does not wait.
    server._ack_budget_ms = 120
    client = _Client(app, server.path)

    class _DialogChordHandlers:
        """Stands in for a chord whose action opens the app's own file dialog."""

        def __init__(self) -> None:
            self.returned_at: float | None = None
            self.dialogs: list[QFileDialog] = []

        def handle(self, method, params):
            dialog = QFileDialog()
            # Offscreen has no portal, so the native dialog cannot be shown at
            # all; the loop it runs is the same one getOpenFileName uses.
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
            dialog.setModal(True)
            self.dialogs.append(dialog)
            # The "human" closes it 700 ms later: far past the ack budget, and
            # far past the point where a client would give up on the reply.
            QTimer.singleShot(700, dialog.reject)
            dialog.exec()
            self.returned_at = time.time()
            return {"ran": True, "action_id": "platform.open_project"}

    handlers = _DialogChordHandlers()
    server._handlers = handlers
    try:
        client.send(
            {"id": 30, "method": "press_keys", "params": {"keys": "ctrl+shift+o"}}
        )
        response = client.wait_line(seconds=3.0)
        assert response is not None, "a call blocked in a modal loop is still answered"
        assert response["id"] == 30
        # The frame was written *inside* the dialog's loop, not after it closed.
        assert client.first_line_at is not None
        assert handlers.returned_at is not None
        assert client.first_line_at < handlers.returned_at, (
            "the answer arrived only after the dialog closed — the request was "
            "held by the modal loop"
        )
        assert response["ok"] is True
        result = response["result"]
        assert result["accepted"] is True
        assert result["answered_early"] is True
        assert result["modal_open"] is True, "the file dialog was on screen"
        assert result["method"] == "press_keys"
        # The late real result is discarded: exactly one frame per request, or
        # the client's line reader would hand a second reply to the next call.
        _pump(app, 0.4)
        assert b"\n" not in client.buffer, "no second reply for one request"
        # The channel kept serving: the connection is not wedged behind the modal.
        client.send({"id": 31, "method": "ping", "params": {}})
        assert client.wait_line()["ok"] is True
    finally:
        for dialog in handlers.dialogs:
            try:
                dialog.reject()
            except Exception:
                pass
        client.close()
        server.stop()


def test_a_second_connection_is_served_inside_the_dialog_loop(tmp_path, monkeypatch):
    """The dialog does not wedge the channel for a *new* peer.

    Qt guards ``readyRead`` against re-entry, so a second line on the *same*
    socket waits for the dialog (the early answer is why that peer is not left
    hanging). A new connection is different: its ``readyRead`` fires inside the
    modal loop and is served, so "is the app still there / read state" after a
    dialog is open works — and the request that owns the in-flight note changes
    under the parked one (see the note-ownership test below).
    """
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setenv("IMGSLI_CONTROL_DIR", str(tmp_path / "ctrl"))
    app = _qapp()
    server = ControlServer(window=_store_window(), app=app)
    assert server.start() is True
    server._ack_budget_ms = 100
    client = _Client(app, server.path)
    second_client: _Client | None = None

    class _DialogAndPingHandlers:
        def handle(self, method, params):
            if method == "ping":  # a read verb really is served nested
                return {"pong": True, "pid": os.getpid()}
            dialog = QFileDialog()
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
            dialog.setModal(True)
            QTimer.singleShot(900, dialog.reject)
            self.dialogs.append(dialog)
            dialog.exec()
            return {"ran": True}

        def __init__(self) -> None:
            self.dialogs: list[QFileDialog] = []

    handlers = _DialogAndPingHandlers()
    server._handlers = handlers
    try:
        client.send({"id": 50, "method": "run_action", "params": {"action_id": "x"}})

        def _connect_and_ping() -> None:
            nonlocal second_client
            second_client = _Client(app, server.path)
            second_client.send({"id": 51, "method": "ping", "params": {}})

        # Sent from inside the dialog's loop: only the nested loop can answer it.
        QTimer.singleShot(300, _connect_and_ping)
        first = client.wait_line(seconds=3.0)
        assert first is not None and first["id"] == 50
        assert first["result"]["answered_early"] is True
        assert second_client is not None, "a peer connected while the dialog was up"
        nested = second_client.wait_line(seconds=3.0)
        assert nested is not None, "a new connection is served during the modal"
        assert nested["id"] == 51
        assert nested["ok"] is True and nested["result"]["pong"] is True
        _pump(app, 0.4)
        assert b"\n" not in client.buffer, "one frame for the parked request"
    finally:
        for dialog in handlers.dialogs:
            try:
                dialog.reject()
            except Exception:
                pass
        if second_client is not None:
            second_client.close()
        client.close()
        server.stop()


def test_a_late_finisher_does_not_erase_a_newer_requests_inflight_note(
    tmp_path, monkeypatch
):
    """A modal loop re-enters ``_handle_line``; the note is one slot.

    The newer request's record is the only evidence left if the app dies in
    *that* call, so the request that finishes late must not clear it.
    """
    from core.control.server import INFLIGHT_NOTE_NAME

    monkeypatch.setenv("IMGSLI_CONTROL_DIR", str(tmp_path / "ctrl"))
    server = ControlServer(window=_store_window(), app=_qapp())
    assert server.start() is True
    note = tmp_path / "ctrl" / INFLIGHT_NOTE_NAME
    try:
        first = server._note_inflight(
            request_id=1, method="press_keys", params={"keys": "ctrl+shift+o"}
        )
        second = server._note_inflight(
            request_id=2, method="ping", params={}
        )
        server._clear_inflight(first)  # the late finisher
        assert note.is_file(), "the newer request still owns the record"
        assert json.loads(note.read_text(encoding="utf-8"))["method"] == "ping"
        server._clear_inflight(second)
        assert not note.exists()
    finally:
        server.stop()


def test_a_failed_handler_that_overran_answers_once_with_the_early_frame(
    tmp_path, monkeypatch
):
    """An overrun answers once; a later failure cannot rewrite that answer.

    The alternative — an ``ok: true`` "accepted" *before* the handler runs —
    would report a refused key delivery as a success. Here the refusal still
    happens first (fast handler → full real reply), and only a handler that is
    still running past the budget is answered on the channel's own initiative.
    """
    from PySide6.QtCore import QEventLoop, QTimer

    monkeypatch.setenv("IMGSLI_CONTROL_DIR", str(tmp_path / "ctrl"))
    app = _qapp()
    server = ControlServer(window=_store_window(), app=app)
    assert server.start() is True
    server._ack_budget_ms = 80
    client = _Client(app, server.path)

    class _SlowFailingHandlers:
        def handle(self, method, params):
            loop = QEventLoop()
            QTimer.singleShot(300, loop.quit)
            loop.exec()
            raise RuntimeError("the dialog's result could not be applied")

    server._handlers = _SlowFailingHandlers()
    try:
        client.send({"id": 40, "method": "run_action", "params": {"action_id": "x"}})
        response = client.wait_line(seconds=2.0)
        assert response is not None
        assert response["id"] == 40, "the early frame carries this request's id"
        assert response["ok"] is True and response["result"]["answered_early"] is True
        _pump(app, 0.4)
        assert b"\n" not in client.buffer, "an error cannot arrive after the answer"
    finally:
        client.close()
        server.stop()


def test_encode_reply_reports_a_frame_it_cannot_emit():
    """Unit-test the reply guard: ``None`` instead of a broken frame."""
    from core.control.server import MAX_REPLY_BYTES, encode_reply

    frame = encode_reply({"id": 1, "ok": True, "result": {"a": 1}})
    assert frame is not None and frame.endswith(b"\n")
    assert json.loads(frame)["result"] == {"a": 1}

    circular: dict = {}
    circular["self"] = circular
    assert encode_reply(circular) is None, "unserialisable result is refused"

    huge = {"blob": "x" * (MAX_REPLY_BYTES + 1)}
    assert encode_reply(huge) is None, "oversized result is refused, not truncated"


def test_foreign_uid_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("IMGSLI_CONTROL_DIR", str(tmp_path / "ctrl"))
    app = _qapp()
    # Inject the checker — never fake a real uid.
    server = ControlServer(
        window=_store_window(), app=app, peer_checker=lambda _fd: False
    )
    assert server.start() is True
    client = _Client(app, server.path)
    try:
        client.send({"id": 13, "method": "ping", "params": {}})
        assert client.wait_line(seconds=1.0) is None, "no reply to a foreign uid"
        assert client.socket.state() != _CONNECTED, "socket closed, not served"
    finally:
        client.close()
        server.stop()


# -- handlers over a live store / registry ---------------------------------


def test_run_action_runs_the_registered_runner(tmp_path):
    calls: list[str] = []
    registry = _registry(_descriptor("platform.fake", lambda: calls.append("ran")))
    handlers = _handlers(_store_window(), registry, tmp_path)

    result = handlers.run_action({"action_id": "platform.fake"})

    assert result == {"ran": True, "action_id": "platform.fake"}
    assert calls == ["ran"], "the registered runner actually executed"


def test_run_action_unknown_id_suggests_a_close_match(tmp_path):
    registry = _registry(_descriptor("platform.settings"))
    handlers = _handlers(_store_window(), registry, tmp_path)

    with pytest.raises(MethodError) as exc:
        handlers.run_action({"action_id": "platform.setings"})

    assert exc.value.hint and "did you mean" in exc.value.hint


def test_open_tab_runs_the_workspace_new_action(tmp_path):
    calls: list[str] = []
    registry = _registry(
        _descriptor("workspace.new_image_gallery", lambda: calls.append("opened")),
        _descriptor("workspace.new_image_compare", lambda: calls.append("other")),
    )
    handlers = _handlers(_store_window(), registry, tmp_path)

    result = handlers.open_tab({"tab": "image_gallery"})

    assert result == {
        "launched": False,
        "reused": True,
        "tab": "image_gallery",
        "action_id": "workspace.new_image_gallery",
        "via": "action",
    }
    assert calls == ["opened"]

    with pytest.raises(MethodError) as exc:
        handlers.open_tab({"tab": "nope"})
    assert "image_gallery" in exc.value.hint


def test_open_tab_falls_back_to_the_session_manager_for_deferred_tabs(
    tmp_path, monkeypatch
):
    """Deferred tabs have no ``workspace.new_*`` action — use the live seam."""
    calls: list[str] = []
    window = types.SimpleNamespace(
        store=Store(),
        app_context=types.SimpleNamespace(
            session_manager=types.SimpleNamespace(
                create_session=lambda session_type: calls.append(session_type)
            )
        ),
    )
    handlers = _handlers(window, _registry(), tmp_path)
    monkeypatch.setattr(handlers, "_tabs", lambda: [("image_gallery", object())])

    result = handlers.open_tab({"tab": "image_gallery"})

    assert calls == ["image_gallery"], "the session manager actually ran"
    assert result["tab"] == "image_gallery"
    assert result["via"] == "session_manager"
    assert result["launched"] is False and result["reused"] is True


def test_get_state_list_sessions_and_list_actions_shapes(tmp_path):
    registry = _registry(
        _descriptor("platform.settings", topic="settings", shortcut="Ctrl+,"),
        _descriptor("image_compare.reset", owner_tab="image_compare"),
    )
    window = _store_window()
    handlers = _handlers(window, registry, tmp_path)

    state = handlers.get_state({})
    assert state["path"] is None
    assert set(state["state"]) == {"settings", "workspace", "document", "tabs"}
    assert all(
        row["active"] is False for row in state["state"]["tabs"].values()
    ), "no discovered tab pages in this process -> inactive slices, not a guess"

    scoped = handlers.get_state({"path": "settings.theme"})
    assert scoped["path"] == "settings.theme"
    assert scoped["state"] == state["state"]["settings"]["theme"]

    with pytest.raises(MethodError):
        handlers.get_state({"path": "settings.nope"})

    sessions = handlers.list_sessions({})
    assert sessions["count"] == len(sessions["sessions"]) >= 1
    assert any(row["session_type"] == "session_picker" for row in sessions["sessions"])

    listed = handlers.list_actions({"query": "settings"})
    assert listed["count"] == 1
    assert listed["actions"][0]["action_id"] == "platform.settings"
    assert listed["actions"][0]["topic"] == "settings"

    assert handlers.list_actions({"owner_tab": "image_compare"})["count"] == 1


def test_list_actions_carries_enabled_and_reason(tmp_path):
    """P2: a not-runnable action surfaces its reason verbatim; default is enabled."""
    registry = _registry(
        _descriptor("image_compare.grid", enabled=False, reason="needs two images"),
        _descriptor("platform.settings"),
    )
    handlers = _handlers(_store_window(), registry, tmp_path)

    rows = {row["action_id"]: row for row in handlers.list_actions({})["actions"]}

    assert rows["image_compare.grid"]["enabled"] is False
    assert rows["image_compare.grid"]["reason"] == "needs two images"
    # Default descriptor ⇒ runnable now, JSON null for "no reason".
    assert rows["platform.settings"]["enabled"] is True
    assert rows["platform.settings"]["reason"] is None

    # Every frozen row key is present, and "no reason" serialises as JSON null.
    for row in rows.values():
        assert {
            "action_id",
            "label",
            "owner_tab",
            "topic",
            "shortcut",
            "enabled",
            "reason",
        } <= set(row)
    serialized = json.loads(json.dumps(handlers.list_actions({})))
    default = next(
        row for row in serialized["actions"] if row["action_id"] == "platform.settings"
    )
    assert default["reason"] is None and default["enabled"] is True


def test_dump_actions_propagates_enabled_and_reason():
    """The snapshot (``--dump-app-snapshot``) carries the same two fields."""
    from devtools.app_snapshot import dump_actions

    rows = {
        row["action_id"]: row
        for row in dump_actions(
            _registry(
                _descriptor("image_compare.grid", enabled=False, reason="needs two images"),
                _descriptor("platform.settings"),
            )
        )
    }

    assert rows["image_compare.grid"]["enabled"] is False
    assert rows["image_compare.grid"]["reason"] == "needs two images"
    assert rows["platform.settings"]["enabled"] is True
    assert rows["platform.settings"]["reason"] is None


def test_read_log_serves_the_live_ring(tmp_path):
    app_logger = logging.getLogger(APP_LOGGER_NAME)
    previous_level = app_logger.level
    app_logger.setLevel(logging.DEBUG)
    ring = LogRing()
    app_logger.addHandler(ring)
    try:
        app_logger.debug("ring debug line")
        app_logger.info("ring info line")
        app_logger.error("ring error line")
        handlers = _handlers(_store_window(), _registry(), tmp_path, ring=ring)

        everything = handlers.read_log({"n": 50})
        assert everything["total_lines"] == 3
        assert [line["text"] for line in everything["lines"]][-1].endswith("ring error line")
        assert [line["level"] for line in everything["lines"]] == ["DEBUG", "INFO", "ERROR"]

        warnings_only = handlers.read_log({"level": "WARNING"})
        assert warnings_only["returned"] == 1
        assert warnings_only["lines"][0]["level"] == "ERROR"

        assert handlers.read_log({"n": 1})["returned"] == 1
    finally:
        app_logger.removeHandler(ring)
        app_logger.setLevel(previous_level)


def test_query_trace_is_honest_without_a_tracer(tmp_path, monkeypatch):
    from core.tracing.tracer import Tracer

    monkeypatch.setattr(Tracer, "_instance", None, raising=False)
    handlers = _handlers(_store_window(), _registry(), tmp_path)

    with pytest.raises(MethodError) as exc:
        handlers.query_trace({})

    assert "IMGSLI_TRACE=1" in (exc.value.hint or "")


def test_set_theme_and_language_validate_and_apply(tmp_path, monkeypatch):
    persisted: list[tuple] = []
    applied: list[str] = []
    handlers = _handlers(_store_window(), _registry(), tmp_path)
    monkeypatch.setattr(
        handlers, "_persist_setting", lambda key, value: persisted.append((key, value))
    )
    monkeypatch.setattr(
        "resources.translations.emit_language_changed",
        lambda language: applied.append(language),
    )

    assert handlers.set_theme({"theme": "dark"}) == {"theme": "dark", "applied": True}
    assert handlers.set_language({"language": "ru"}) == {"language": "ru", "applied": True}
    assert persisted == [("theme", "dark"), ("language", "ru")]
    assert applied == ["ru"], "the live language seam was called"

    with pytest.raises(MethodError):
        handlers.set_theme({"theme": "neon"})
    with pytest.raises(MethodError):
        handlers.set_language({"language": "klingon"})


def test_set_theme_applies_through_the_live_app_context_seam(tmp_path, monkeypatch):
    calls: list[object] = []
    window = types.SimpleNamespace(
        store=Store(),
        app_context=types.SimpleNamespace(
            apply_theme_to_app=lambda app: calls.append(app)
        ),
    )
    handlers = _handlers(window, _registry(), tmp_path, app="THE_APP")
    monkeypatch.setattr(handlers, "_persist_setting", lambda key, value: None)

    assert handlers.set_theme({"theme": "light"})["applied"] is True
    assert calls == ["THE_APP"], "theme applied via ApplicationContext.apply_theme_to_app"


def test_open_folder_requires_an_existing_directory(tmp_path):
    handlers = _handlers(_store_window(), _registry(), tmp_path)

    with pytest.raises(MethodError) as exc:
        handlers.open_folder({"path": str(tmp_path / "does-not-exist")})

    assert "not an existing directory" in exc.value.message


class _DropTab:
    """Handler-level tab stand-in: takes files, never a directory."""

    def __init__(self) -> None:
        self.dropped: list[list] = []

    def accepts_drop(self, paths):
        paths = list(paths)
        return bool(paths) and all(path.is_file() for path in paths)

    def handle_drop(self, paths):
        self.dropped.append(list(paths))
        return True


def _series_folder(tmp_path):
    folder = tmp_path / "series"
    folder.mkdir()
    (folder / "1.png").write_bytes(b"x")
    (folder / "2.jpg").write_bytes(b"x")
    (folder / "readme.txt").write_bytes(b"x")
    return folder


def test_open_folder_can_target_a_file_only_tab(tmp_path, monkeypatch):
    """multi_compare's 'add images' dialog is unreachable headlessly; the
    control surface must be able to feed it by naming the tab."""
    folder = _series_folder(tmp_path)
    handlers = _handlers(_store_window(), _registry(), tmp_path)
    mc = _DropTab()
    monkeypatch.setattr(handlers, "_tabs", lambda: [("multi_compare", mc)])
    monkeypatch.setattr(
        handlers, "_tab_kinds", lambda: ["image_gallery", "multi_compare"]
    )

    result = handlers.open_folder({"path": str(folder), "tab": "multi_compare"})

    assert result == {
        "routed": True,
        "path": str(folder),
        "tab": "multi_compare",
        "images": 2,
    }
    assert [p.name for p in mc.dropped[-1]] == ["1.png", "2.jpg"]


def test_open_folder_target_opens_the_tab_when_absent(tmp_path, monkeypatch):
    folder = _series_folder(tmp_path)
    handlers = _handlers(_store_window(), _registry(), tmp_path)
    mc = _DropTab()
    live: list = []
    actions: list = []
    monkeypatch.setattr(handlers, "_tabs", lambda: list(live))
    monkeypatch.setattr(handlers, "_tab_kinds", lambda: ["multi_compare"])

    def _run_action(action_id: str) -> None:
        actions.append(action_id)
        live.append(("multi_compare", mc))

    monkeypatch.setattr(handlers, "_run_action_id", _run_action)

    result = handlers.open_folder({"path": str(folder), "tab": "multi_compare"})

    assert actions == ["workspace.new_multi_compare"]
    assert result["tab"] == "multi_compare" and result["images"] == 2


def test_open_folder_target_rejects_an_unknown_kind(tmp_path, monkeypatch):
    handlers = _handlers(_store_window(), _registry(), tmp_path)
    monkeypatch.setattr(handlers, "_tabs", lambda: [])
    monkeypatch.setattr(handlers, "_tab_kinds", lambda: ["multi_compare"])

    with pytest.raises(MethodError) as exc:
        handlers.open_folder({"path": str(tmp_path), "tab": "wibble"})

    assert "unknown tab kind" in exc.value.message
    assert "open_tab" in exc.value.hint


def test_list_surfaces_includes_devtool_demos_as_not_live(tmp_path):
    handlers = _handlers(_store_window(), _registry(), tmp_path)

    surfaces = handlers.list_surfaces({})

    assert surfaces["count"] == len(surfaces["surfaces"])
    assert all("live" in row for row in surfaces["surfaces"])


def test_press_keys_unknown_key_name_gets_an_allowlist_hint(tmp_path):
    handlers = _handlers(_store_window(), _registry(), tmp_path)

    with pytest.raises(MethodError) as exc:
        handlers.press_keys({"keys": "Ctrl+Wibble"})

    assert "unknown key" in exc.value.message
    assert "valid names" in exc.value.hint and "f12" in exc.value.hint


def test_press_keys_ctrl_shift_p_maps_to_qt_key_and_modifiers():
    from PySide6.QtCore import Qt

    from core.control.discovery import parse_key_sequence

    (key, modifiers, label), = parse_key_sequence("ctrl+shift+p")

    assert key == Qt.Key.Key_P
    assert modifiers == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    assert label == "ctrl+shift+p"
    assert [combo for _k, _m, combo in parse_key_sequence("Down,Down,Enter")] == [
        "Down",
        "Down",
        "Enter",
    ]


def test_press_keys_refuses_when_there_is_no_target(tmp_path):
    # A fake app with no active window and no main window ⇒ honest refusal.
    app = types.SimpleNamespace(activeWindow=lambda: None)
    handlers = _handlers(None, _registry(), tmp_path, app=app)

    with pytest.raises(MethodError) as exc:
        handlers.press_keys({"keys": "Right"})

    assert "no live window" in exc.value.message


def test_press_keys_refuses_when_the_window_is_not_os_active(tmp_path):
    """Complaint mcp-c-015: a key typed at a background window answered ``ok``.

    Measured 2026-10-22 on a private display without a window manager, right
    after boot: ``press_keys {"keys": "ctrl+shift+p"}`` answered ``ok`` and no
    Find Action window appeared; after ``xdotool windowfocus <main>`` the same
    call opened it. The window exists and Qt hands the key to a real widget, so
    the old code reported delivery for a key the window system dropped — two
    false "dead chord" verdicts in a shortcut sweep.
    """
    from PySide6.QtWidgets import QListWidget

    app = _qapp()
    widget = QListWidget()
    widget.addItems(["a", "b"])
    widget.resize(120, 80)
    widget.show()
    _pump(app, 0.05)
    widget.setFocus()
    _pump(app, 0.05)

    # The measured state: the window is there, the display reports no active
    # window — a real key would reach nobody.
    inactive = types.SimpleNamespace(activeWindow=lambda: None)
    handlers = _handlers(widget, _registry(), tmp_path, app=inactive)
    try:
        with pytest.raises(MethodError) as exc:
            handlers.press_keys({"keys": "Down"})
        assert "not the OS-active window" in exc.value.message
        assert "windowfocus" in exc.value.hint, exc.value.hint
        assert "nav_key" in exc.value.hint, exc.value.hint
    finally:
        widget.close()


def test_press_keys_reports_the_focus_it_typed_into(tmp_path):
    """The active path still delivers, and now names the keyboard owner.

    ``activated`` / ``focus_is_ours`` are the fields ``nav_key`` reports for the
    same question, so a client reads the state instead of inferring it from
    ``ok``. ``activated`` is False here: the window already held focus, so the
    call had nothing to bring forward.
    """
    from PySide6.QtWidgets import QListWidget

    app = _qapp()
    widget = QListWidget()
    widget.addItems(["a", "b"])
    widget.resize(120, 80)
    widget.show()
    _pump(app, 0.05)
    widget.setCurrentRow(0)
    widget.setFocus()
    _pump(app, 0.05)

    handlers = _handlers(widget, _registry(), tmp_path, app=app)
    try:
        result = handlers.press_keys({"keys": "Down"})
        _pump(app, 0.05)
        assert widget.currentRow() == 1, "the key still reaches the focus widget"
        assert result["activated"] is False, "an active window is not activated again"
        assert result["focus_is_ours"] is True
    finally:
        widget.close()


def test_press_keys_reaches_the_focused_widget(tmp_path):
    """The injection reaches the app: keys go through the real Qt key pipeline.

    A stock focusable widget stands in for a tab widget: the point is that
    ``press_keys`` delivers to the live focus widget and Qt *acts* on it
    (selection moves), not merely that the parser accepted the names. Tab-owned
    widgets are intentionally not imported here — root ``tests/`` must not
    deep-import a tab's internals (``test_root_tests_no_tab_internals_leak``).
    """
    from PySide6.QtWidgets import QListWidget

    app = _qapp()
    widget = QListWidget()
    widget.addItems(["a", "b", "c"])
    widget.resize(200, 150)
    widget.show()
    _pump(app, 0.05)
    widget.setCurrentRow(0)
    widget.setFocus()
    _pump(app, 0.05)

    handlers = _handlers(widget, _registry(), tmp_path, app=app)
    try:
        result = handlers.press_keys({"keys": "Down"})
        _pump(app, 0.05)
        assert widget.currentRow() == 1, "Down actually moved the live selection"
        assert result["pressed"] == ["Down"]
        assert result["count"] == 1
        assert result["target"]

        handlers.press_keys({"keys": "End"})
        _pump(app, 0.05)
        assert widget.currentRow() == 2
    finally:
        widget.close()


@pytest.mark.skipif(
    not _CAPTURE_READY,
    reason="capture_live needs a private non-:0 display (a private Xvfb)",
)
def test_capture_live_writes_a_non_empty_png(tmp_path):
    app = _qapp()
    widget = QWidget()
    widget.store = Store()
    widget.resize(120, 80)
    widget.show()
    _pump(app, 1.0)
    handlers = _handlers(widget, _registry(), tmp_path, app=app)
    try:
        result = handlers.capture_live({})

        path = result["path"]
        assert result["what"]
        assert result["method"] in ("grabWindow", "widget_grab")
        assert result["size"][0] > 0 and result["size"][1] > 0
        assert os.path.getsize(path) > 0
        with open(path, "rb") as handle:
            assert handle.read(8) == b"\x89PNG\r\n\x1a\n"
        # No canvas under this bare widget -> nothing composited, and the
        # key is still reported (honest, not omitted).
        assert result["rhi_layers"] == 0
    finally:
        widget.close()


class _FakeCanvas:
    """Duck-typed canvas stand-in: the compositing path touches only these."""

    def __init__(
        self,
        *,
        visible: bool = True,
        size: tuple[int, int] = (20, 10),
        anchor: tuple[int, int] = (5, 4),
        image: QImage | None = None,
        boom: bool = False,
    ) -> None:
        self._visible = visible
        self._size = size
        self._anchor = anchor
        self._image = image
        self._boom = boom

    def isVisible(self) -> bool:  # noqa: N802 - Qt name
        return self._visible

    def width(self) -> int:
        return self._size[0]

    def height(self) -> int:
        return self._size[1]

    def mapToGlobal(self, _point):  # noqa: N802 - Qt name
        return QPoint(*self._anchor)

    def grabFramebuffer(self):  # noqa: N802 - Qt name
        if self._boom:
            raise RuntimeError("no composited frame")
        return self._image


class _FakeTarget:
    """A widget wearing only ``findChildren`` + ``mapFromGlobal``."""

    def __init__(self, canvases) -> None:
        self._canvases = list(canvases)

    def findChildren(self, _cls):  # noqa: N802 - Qt name
        return list(self._canvases)

    def mapFromGlobal(self, point):  # noqa: N802 - Qt name
        return point


def _solid(size, color) -> QImage:
    image = QImage(size[0], size[1], QImage.Format.Format_RGBA8888)
    image.fill(color)
    return image


def test_compose_rhi_frames_paints_a_visible_canvas_at_its_geometry() -> None:
    """The blind spot: a presenting canvas is absent from both grab paths."""
    _qapp()
    pixmap = QPixmap(100, 80)
    pixmap.fill(QColor(0, 0, 0))
    canvas = _FakeCanvas(size=(20, 10), anchor=(5, 4), image=_solid((4, 3), QColor(255, 0, 0)))

    assert capture.compose_rhi_frames(_FakeTarget([canvas]), pixmap) == 1

    image = pixmap.toImage()
    assert image.pixelColor(6, 5).red() > 200, "the canvas frame landed at its anchor"
    assert image.pixelColor(90, 70).red() < 50, "and nothing else was painted"


def test_compose_rhi_frames_skips_hidden_null_and_raising_canvases() -> None:
    """A capture must never fail (or paint garbage) because of one canvas."""
    _qapp()
    pixmap = QPixmap(60, 40)
    pixmap.fill(QColor(0, 0, 0))
    canvases = [
        _FakeCanvas(visible=False, image=_solid((4, 3), QColor(0, 255, 0))),
        _FakeCanvas(image=None),
        _FakeCanvas(boom=True),
    ]

    assert capture.compose_rhi_frames(_FakeTarget(canvases), pixmap) == 0
    assert pixmap.toImage().pixelColor(10, 10).green() < 50


def test_compose_rhi_frames_tolerates_a_target_without_canvases() -> None:
    """A raising/absent child query is not a capture failure."""
    _qapp()
    pixmap = QPixmap(8, 8)
    pixmap.fill(QColor(0, 0, 0))

    class _Broken:
        def findChildren(self, _cls):  # noqa: N802 - Qt name
            raise RuntimeError("no children here")

    assert capture.compose_rhi_frames(_Broken(), pixmap) == 0


class _FakeWindow:
    """Top-level stand-in: the canvases hang off the window, not the page."""

    def __init__(self, canvases) -> None:
        self._canvases = list(canvases)

    def findChildren(self, _cls):  # noqa: N802 - Qt name
        return list(self._canvases)


class _PageOnWindow(_FakeTarget):
    def __init__(self, canvases, offset: tuple[int, int]) -> None:
        super().__init__([])  # the page itself owns no canvas child
        self._window = _FakeWindow(canvases)
        self._offset = offset

    def window(self):
        return self._window

    def mapFromGlobal(self, point):  # noqa: N802 - Qt name
        return QPoint(point.x() - self._offset[0], point.y() - self._offset[1])


def test_compose_rhi_frames_finds_a_canvas_over_a_page() -> None:
    """The Quick Look canvas is parented to the window, not to the page.

    Capturing a tab page must still composite it (the overlay rides the
    window), and the frame lands at the page-local anchor.
    """
    _qapp()
    pixmap = QPixmap(100, 80)
    pixmap.fill(QColor(0, 0, 0))
    canvas = _FakeCanvas(size=(20, 10), anchor=(30, 40), image=_solid((4, 3), QColor(0, 0, 255)))
    page = _PageOnWindow([canvas], offset=(20, 36))

    assert capture.compose_rhi_frames(page, pixmap) == 1
    assert pixmap.toImage().pixelColor(12, 6).blue() > 200


def test_compose_rhi_frames_skips_a_canvas_off_the_grab() -> None:
    """A canvas elsewhere in the window must not bleed into the page grab."""
    _qapp()
    pixmap = QPixmap(50, 40)
    pixmap.fill(QColor(0, 0, 0))
    canvas = _FakeCanvas(size=(20, 10), anchor=(500, 500), image=_solid((4, 3), QColor(255, 255, 0)))

    assert capture.compose_rhi_frames(_FakeTarget([canvas]), pixmap) == 0
    assert pixmap.toImage().pixelColor(10, 10).red() < 50
