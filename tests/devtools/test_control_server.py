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

from PySide6.QtNetwork import QLocalSocket
from PySide6.QtWidgets import QApplication, QWidget

from core.actions.types import ActionDescriptor
from core.control import discovery
from core.control.handlers import ControlHandlers, MethodError
from core.control.server import ControlServer, LogRing
from core.store import Store
from ui.actions.registry import ActionRegistry

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
        self.socket = QLocalSocket()
        self.socket.readyRead.connect(self._read)
        self.socket.connectToServer(str(path))
        _pump(app, 3.0, lambda: self.socket.state() == _CONNECTED)

    def _read(self) -> None:
        chunk = self.socket.readAll()
        self.buffer += chunk.data() if chunk is not None else b""

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
    assert set(state["state"]) == {"settings", "workspace", "document"}

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


def test_read_log_serves_the_live_ring(tmp_path):
    app_logger = logging.getLogger("ImproveImgSLI")
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
    finally:
        widget.close()
