"""DnD delivery composition: carry/row-drag precedence, target stacking, window-drop consent.

Guards: symmetric carry/row-drag precedence (start_drag cancels carry like
begin cancels drag; Escape unwinds both), drop-target z-order over
registration order, window drop consulting tab consent before accept, and the
150 ms fallback pinned to the drop-time session (no blind cross-session load).

Uses real services with forced gesture flags where the public API now makes
both-active unreachable by construction (the symmetric cancels).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import (
    QEvent,
    QMimeData,
    QPoint,
    QPointF,
    QRect,
    Qt,
    QUrl,
)
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

from events.drag_drop_handler import DragAndDropService
from events.image_carry import ImageCarryService


@pytest.fixture(autouse=True)
def _reset_dnd_singletons(monkeypatch):
    monkeypatch.setattr(DragAndDropService, "_instance", None)
    monkeypatch.setattr(ImageCarryService, "_instance", None)
    yield
    DragAndDropService._instance = None
    ImageCarryService._instance = None


def _doc_store():
    document = SimpleNamespace(
        image_list1=[SimpleNamespace(rating=0)] * 4,
        image_list2=[SimpleNamespace(rating=0)] * 4,
    )
    return SimpleNamespace(get_session_state_slot=lambda _slot: document)


def _red_image(tmp_path: Path) -> Path:
    from PySide6.QtGui import QPixmap

    img = tmp_path / "shot.png"
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.red)
    pix.save(str(img), "PNG")
    return img


def _make_row():
    from ui.widgets.rating_item import RatingListItem

    return RatingListItem(
        index=0,
        text="shot.png",
        rating=1,
        full_path="/tmp/shot.png",
        list_num=1,
        get_rating=lambda *args, **kwargs: 1,
        increment_rating=lambda *args, **kwargs: None,
        decrement_rating=lambda *args, **kwargs: None,
        create_rating_gesture=lambda *args, **kwargs: None,
        on_update_drop_indicator=lambda *args, **kwargs: None,
        on_clear_drop_indicator=lambda: None,
        is_current=True,
    )


def _mouse_move(pos: QPointF = QPointF(10, 10)):
    return QMouseEvent(
        QEvent.Type.MouseMove,
        pos,
        pos,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _escape_press():
    return QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
    )


def test_start_drag_cancels_active_carry(qapp, tmp_path):
    """start_drag cancels carry — the mirror of begin() cancelling drag."""
    from events import router

    host = QWidget()
    host.show()
    carry = ImageCarryService(SimpleNamespace(), host)
    assert carry.begin([_red_image(tmp_path)]) is True
    assert carry.is_active()

    dnd = DragAndDropService(_doc_store(), parent=host)
    row = _make_row()
    event = SimpleNamespace(
        globalPosition=lambda: QPointF(50, 50), position=lambda: QPointF(5, 5)
    )
    dnd.start_drag(row, event)

    assert dnd.is_dragging()
    assert not carry.is_active()
    # Router now sees the established drag, not the dead carry.
    assert router.route_drag_and_drop_override(None, _mouse_move(), dnd) is True
    dnd._cleanup()
    row.deleteLater()
    host.deleteLater()


def test_escape_unwinds_both_carry_and_drag(qapp):
    """Escape with both gestures flagged clears both, swallowing the key."""
    from events import router

    host = QWidget()
    carry = ImageCarryService(SimpleNamespace(), host)
    carry._active = True
    carry._armed = True
    dnd = DragAndDropService(_doc_store(), parent=host)
    dnd._is_dragging = True

    assert router.route_drag_and_drop_override(None, _escape_press(), dnd) is True

    assert not carry.is_active()
    assert not dnd.is_dragging()
    host.deleteLater()


def test_active_drag_keeps_precedence_over_carry(qapp):
    """Both-active MouseMove goes to the row-drag, never the carry."""
    from events import router

    host = QWidget()
    carry = ImageCarryService(SimpleNamespace(), host)
    carry._active = True
    carry._armed = True
    dnd = DragAndDropService(_doc_store(), parent=host)
    dnd._is_dragging = True
    dnd._ghost_widget = SimpleNamespace(move=lambda *_a: None, raise_=lambda: None)

    seen: list[str] = []
    carry.update_position = lambda _e: seen.append("carry")  # type: ignore[method-assign]
    dnd.update_drag_position = lambda _e: seen.append("drag")  # type: ignore[method-assign]

    assert router.route_drag_and_drop_override(None, _mouse_move(), dnd) is True
    assert seen == ["drag"]
    host.deleteLater()


def _fake_target(name: str, record: list):
    return SimpleNamespace(
        name=name,
        isVisible=lambda: True,
        mapFromGlobal=lambda _p: QPoint(1, 1),
        rect=lambda: QRect(0, 0, 10, 10),
        can_accept_drop=lambda _data: True,
        update_drop_indicator=lambda _pos: record.append(name),
        clear_drop_indicator=lambda: record.append(f"clear:{name}"),
    )


def test_drop_target_z_order_beats_registration_order(qapp, monkeypatch):
    """Topmost (widgetAt chain) target wins even when registered first."""
    host = QWidget()
    service = DragAndDropService(_doc_store(), parent=host)
    service._is_dragging = True
    service._ghost_widget = SimpleNamespace(move=lambda *_a: None, raise_=lambda: None)
    record: list[str] = []
    front = _fake_target("front", record)
    back = _fake_target("back", record)
    service._drop_targets = [front, back]  # registration order prefers back

    child = SimpleNamespace(parentWidget=lambda: front)
    monkeypatch.setattr(
        QApplication, "widgetAt", staticmethod(lambda *_a: child)
    )

    event = SimpleNamespace(globalPosition=lambda: QPointF(3, 3))
    service.update_drag_position(event)

    assert service._current_target is front
    assert "front" in record
    host.deleteLater()


def test_drop_target_falls_back_to_registration_order(qapp, monkeypatch):
    """widgetAt None (headless): containment scan still resolves a target."""
    host = QWidget()
    service = DragAndDropService(_doc_store(), parent=host)
    service._is_dragging = True
    service._ghost_widget = SimpleNamespace(move=lambda *_a: None, raise_=lambda: None)
    record: list[str] = []
    back = _fake_target("back", record)
    front = _fake_target("front", record)
    service._drop_targets = [back, front]

    monkeypatch.setattr(QApplication, "widgetAt", staticmethod(lambda *_a: None))

    event = SimpleNamespace(globalPosition=lambda: QPointF(3, 3))
    service.update_drag_position(event)

    assert service._current_target is front  # reversed registration order
    host.deleteLater()


def test_drop_target_skips_dead_target(qapp, monkeypatch):
    """A target whose wrapper is dead is skipped, never selected."""
    import shiboken6

    host = QWidget()
    service = DragAndDropService(_doc_store(), parent=host)
    service._is_dragging = True
    service._ghost_widget = SimpleNamespace(move=lambda *_a: None, raise_=lambda: None)
    record: list[str] = []
    live = _fake_target("live", record)
    dead_widget = QWidget()
    dead_widget.deleteLater()
    QApplication.sendPostedEvents(dead_widget, QEvent.Type.DeferredDelete)
    assert not shiboken6.isValid(dead_widget)
    service._drop_targets = [dead_widget, live]

    monkeypatch.setattr(QApplication, "widgetAt", staticmethod(lambda *_a: None))
    # Fallback containment scan: isVisible() on the dead wrapper raises
    # RuntimeError first, so the dead target is skipped without touching it.

    event = SimpleNamespace(globalPosition=lambda: QPointF(3, 3))
    service.update_drag_position(event)

    assert service._current_target is live
    host.deleteLater()


def _mime_with_file(path: str) -> QMimeData:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(path)])
    return mime


def _window_handler(store, main_window, widget=None):
    from events.window_event_handler import WindowEventHandler

    return WindowEventHandler(store, main_controller=None, widget=widget)


def _consent_store(session_type: str = "image_compare", session_id: str = "s1"):
    session = SimpleNamespace(session_type=session_type, id=session_id)
    return SimpleNamespace(
        get_active_workspace_session=lambda: session,
        viewport=SimpleNamespace(view_state=SimpleNamespace(is_horizontal=False)),
    )


def _consent_window(accept: bool):
    calls: list[list] = []
    tab = SimpleNamespace(
        accepts_drop=lambda paths: (calls.append(list(paths)), accept)[1]
    )
    registry = SimpleNamespace(get_tab=lambda _t: tab)
    window = SimpleNamespace(ui=SimpleNamespace(_tab_registry=registry))
    return window, calls


def test_window_enter_ignores_when_tab_declines(qapp, tmp_path):
    img = str(tmp_path / "a.png")
    Path(img).write_bytes(b"x")
    handler = _window_handler(_consent_store(), *_consent_window(False)[:1])
    handler.main_window, _ = _consent_window(False)
    overlays: list[bool] = []
    handler.widget = SimpleNamespace(
        is_drag_overlay_visible=lambda: False,
        update_drag_overlays=lambda _h, visible: overlays.append(visible),
    )

    mime = _mime_with_file(img)
    event = QDragEnterEvent(
        QPoint(5, 5), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
    )
    handler.handle_drag_enter(event)

    assert not event.isAccepted()
    assert overlays == []


def test_window_enter_accepts_when_tab_consents(qapp, tmp_path):
    img = str(tmp_path / "a.png")
    Path(img).write_bytes(b"x")
    handler = _window_handler(_consent_store(), None)
    handler.main_window, calls = _consent_window(True)
    overlays: list[bool] = []
    handler.widget = SimpleNamespace(
        is_drag_overlay_visible=lambda: False,
        update_drag_overlays=lambda _h, visible: overlays.append(visible),
    )

    mime = _mime_with_file(img)
    event = QDragEnterEvent(
        QPoint(5, 5), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
    )
    handler.handle_drag_enter(event)

    assert event.isAccepted()
    assert overlays == [True]
    assert [str(p) for p in calls[0]] == [img]


def test_drop_fallback_skips_after_session_switch(qapp, tmp_path, monkeypatch):
    """150 ms fallback fires only when the drop-time session is still active."""
    import events.window_event_handler as weh

    img = str(tmp_path / "a.png")
    Path(img).write_bytes(b"x")
    state = {"active": SimpleNamespace(session_type="x", id="s1")}
    store = SimpleNamespace(
        get_active_workspace_session=lambda: state["active"],
        viewport=SimpleNamespace(view_state=SimpleNamespace(is_horizontal=False)),
    )
    loads: list[tuple] = []
    controller = SimpleNamespace(
        sessions=SimpleNamespace(
            load_images_from_paths=lambda paths, slot: loads.append(
                (list(paths), slot)
            )
        )
    )
    fake_registry = SimpleNamespace(
        get_tab=lambda _t: SimpleNamespace(accepts_drop=lambda _p: False),
        route_drop=lambda *_a, **_k: False,
    )
    window = SimpleNamespace(ui=SimpleNamespace(_tab_registry=fake_registry))
    handler = weh.WindowEventHandler(store, controller, None, parent=None)
    handler.main_window = window

    fired: list[tuple[int, object]] = []

    class _StubTimer:
        @staticmethod
        def singleShot(delay, fn):
            fired.append((delay, fn))

    monkeypatch.setattr(weh, "QTimer", _StubTimer)

    mime = _mime_with_file(img)
    event = QDropEvent(
        QPointF(5, 5), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
    )
    handler.handle_drop(event)

    assert len(fired) == 1
    delay, fn = fired[0]
    assert delay == 150

    # Session switched mid-flight → no blind cross-session load.
    state["active"] = SimpleNamespace(session_type="x", id="s2")
    fn()
    assert loads == []

    # Same session still active → loads with drop-time payload identity.
    state["active"] = SimpleNamespace(session_type="x", id="s1")
    fn()
    assert loads == [([img], 1)]


def test_drop_fallback_guards_dead_controller(qapp, tmp_path, monkeypatch):
    """Fallback with no/dead controller is a silent no-op, never a crash."""
    import events.window_event_handler as weh

    img = str(tmp_path / "a.png")
    Path(img).write_bytes(b"x")
    store = SimpleNamespace(
        get_active_workspace_session=lambda: SimpleNamespace(
            session_type="x", id="s1"
        ),
        viewport=SimpleNamespace(view_state=SimpleNamespace(is_horizontal=False)),
    )
    fake_registry = SimpleNamespace(
        get_tab=lambda _t: SimpleNamespace(accepts_drop=lambda _p: False),
        route_drop=lambda *_a, **_k: False,
    )
    window = SimpleNamespace(ui=SimpleNamespace(_tab_registry=fake_registry))
    handlers = [
        weh.WindowEventHandler(store, controller, None, parent=None)
        for controller in (None, SimpleNamespace(sessions=None))
    ]
    for handler in handlers:
        handler.main_window = window

    fired: list[tuple[int, object]] = []

    class _StubTimer:
        @staticmethod
        def singleShot(delay, fn):
            fired.append((delay, fn))

    monkeypatch.setattr(weh, "QTimer", _StubTimer)

    for handler in handlers:
        mime = _mime_with_file(img)
        event = QDropEvent(
            QPointF(5, 5), Qt.DropAction.CopyAction, mime,
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        )
        handler.handle_drop(event)  # must not raise

    assert len(fired) == 2
    for _delay, fn in fired:
        fn()  # must not raise
