"""Events P2: Shift/Space routing contract, DND delay gating, mouse dedup.

Covers ``task-fix-events-p2-2026-09-20``:
- ``should_route_globally`` denies unknown keys (dead tail predicate removed).
- Shift routes globally only while space is held (ordering contract).
- ``IMGSLI_DND_ENTER_DELAY_MS`` never sleeps the prod drag-enter path;
  it is honored only under ``IMGSLI_DND_DEBUG``.
- Mouse press/release fan-out dedups by event identity + monotonic
  sequence — no ``id()`` in any key path.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QMouseEvent


def _key_event(key):
    return SimpleNamespace(key=lambda: key)


@pytest.fixture(autouse=True)
def _reset_dnd_singletons(monkeypatch):
    from events.drag_drop_handler import DragAndDropService
    from events.image_carry import ImageCarryService

    monkeypatch.setattr(DragAndDropService, "_instance", None)
    monkeypatch.setattr(ImageCarryService, "_instance", None)
    yield
    DragAndDropService._instance = None
    ImageCarryService._instance = None


def _route_store(*, space_pressed: bool = False):
    return SimpleNamespace(
        viewport=SimpleNamespace(
            interaction_state=SimpleNamespace(space_bar_pressed=space_pressed),
        ),
    )


def _global_keyboard(store):
    from events.app_event.keyboard import GlobalKeyboardHandler
    from events.keyboard_state_service import KeyboardStateService

    return GlobalKeyboardHandler(
        store,
        presenter_provider=lambda: None,
        movement_controller=SimpleNamespace(start=lambda: None, stop=lambda: None),
        keyboard_state=KeyboardStateService(store),
    )


def test_should_route_globally_denies_untracked_key():
    """Dead tail predicate removed: unknown keys are denied, not re-matched."""
    keyboard = _global_keyboard(_route_store())
    assert keyboard.should_route_globally(_key_event(Qt.Key.Key_F), None) is False


def test_should_route_globally_overlay_and_space():
    keyboard = _global_keyboard(_route_store())
    assert keyboard.should_route_globally(_key_event(Qt.Key.Key_W), None) is True
    assert keyboard.should_route_globally(_key_event(Qt.Key.Key_Space), None) is True


def test_shift_routes_only_while_space_held():
    assert (
        _global_keyboard(_route_store(space_pressed=False)).should_route_globally(
            _key_event(Qt.Key.Key_Shift), None
        )
        is False
    )
    assert (
        _global_keyboard(_route_store(space_pressed=True)).should_route_globally(
            _key_event(Qt.Key.Key_Shift), None
        )
        is True
    )


def _mouse_press():
    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(10, 10),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _mouse_release():
    return QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(10, 10),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _p2_event_handler():
    from events.app_event_handler import EventHandler
    from events.drag_drop_handler import DragAndDropService

    doc = SimpleNamespace(image_list1=[], image_list2=[])
    DragAndDropService(
        SimpleNamespace(get_session_state_slot=lambda _slot: doc), parent=None
    )
    store = SimpleNamespace(
        viewport=SimpleNamespace(
            view_state=SimpleNamespace(showing_single_image_mode=0),
            interaction_state=SimpleNamespace(
                pressed_keys=set(),
                space_bar_pressed=False,
                last_horizontal_movement_key=None,
                last_vertical_movement_key=None,
                last_spacing_movement_key=None,
            ),
        ),
        emit_viewport_change=lambda *_a, **_k: None,
    )
    presenter = SimpleNamespace(main_window_app=None, image_label_handler=None)
    return EventHandler(store, presenter)


def test_mouse_dedup_emits_once_per_physical_event(qapp):
    """Same QMouseEvent object delivered twice emits once (identity dedup)."""
    handler = _p2_event_handler()
    presses: list = []
    handler.mouse_press_event_signal.connect(lambda _e: presses.append(1))

    event = _mouse_press()
    watched = QWidget()
    handler.eventFilter(watched, event)
    handler.eventFilter(watched, event)
    assert len(presses) == 1
    assert handler._last_mouse_press_seq == 1

    handler.eventFilter(watched, _mouse_press())
    assert len(presses) == 2
    assert handler._last_mouse_press_seq == 2


def test_mouse_release_dedup_symmetric(qapp):
    handler = _p2_event_handler()
    releases: list = []
    handler.mouse_release_event_signal.connect(lambda _e: releases.append(1))

    event = _mouse_release()
    watched = QWidget()
    handler.eventFilter(watched, event)
    handler.eventFilter(watched, event)
    assert len(releases) == 1
    assert handler._last_mouse_release_seq >= 1

    handler.eventFilter(watched, _mouse_release())
    assert len(releases) == 2


def test_mouse_dedup_eventfilter_single_emit(qapp):
    """Press and release sequences share one monotonic counter, no id()."""
    import ast

    from events.app_event_handler import EventHandler  # noqa: F401

    text = None
    repo = __import__("pathlib").Path(__file__).resolve().parents[2]
    for relative in (
        "src/events/app_event_handler.py",
        "src/events/app_event/keyboard.py",
        "src/events/window_event_handler.py",
    ):
        tree = ast.parse((repo / relative).read_text())
        id_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "id"
        ]
        assert not id_calls, f"no id() in any key path ({relative})"

    handler = _p2_event_handler()
    presses: list = []
    handler.mouse_press_event_signal.connect(lambda _e: presses.append(1))
    handler.eventFilter(QWidget(), _mouse_press())
    assert len(presses) == 1
    assert handler._last_mouse_press_seq == 1


def test_dnd_enter_delay_never_sleeps_without_debug(qapp, monkeypatch):
    from events import window_event_handler as weh

    calls: list = []
    monkeypatch.setattr("time.sleep", lambda s: calls.append(s))
    monkeypatch.setenv("IMGSLI_DND_ENTER_DELAY_MS", "100")
    monkeypatch.delenv("IMGSLI_DND_DEBUG", raising=False)
    monkeypatch.delenv("IMGSLI_IMAGE_COMPARE_DEBUG", raising=False)
    monkeypatch.delenv("IMGSLI_IC_DEBUG", raising=False)

    ignored: list = []
    event = SimpleNamespace(
        mimeData=lambda: SimpleNamespace(hasUrls=lambda: False),
        ignore=lambda: ignored.append(1),
    )
    handler = weh.WindowEventHandler(
        SimpleNamespace(), main_controller=None, widget=None, parent=None
    )
    handler.handle_drag_enter(event)
    assert ignored == [1]
    assert calls == [], "prod drag-enter must never sleep on IMGSLI_DND_ENTER_DELAY_MS"


def test_dnd_enter_delay_honored_under_dnd_debug(qapp, monkeypatch):
    from events import window_event_handler as weh

    calls: list = []
    monkeypatch.setattr("time.sleep", lambda s: calls.append(s))
    monkeypatch.setenv("IMGSLI_DND_ENTER_DELAY_MS", "100")
    monkeypatch.setenv("IMGSLI_DND_DEBUG", "1")

    ignored: list = []
    event = SimpleNamespace(
        mimeData=lambda: SimpleNamespace(hasUrls=lambda: False),
        ignore=lambda: ignored.append(1),
    )
    handler = weh.WindowEventHandler(
        SimpleNamespace(), main_controller=None, widget=None, parent=None
    )
    handler.handle_drag_enter(event)
    assert ignored == [1]
    assert calls == [pytest.approx(0.1)]
