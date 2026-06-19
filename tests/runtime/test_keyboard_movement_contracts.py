"""Keyboard movement owns received WASD/QE signals symmetrically.

Dogma source: docs/dev/CONTRACTS.md §Viewport & Interaction.
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import Qt

from events.app_event.keyboard import GlobalKeyboardHandler
from events.canvas_input.owner_ids import KEYBOARD_MOVE_OWNER
from events.image_label.keyboard import ImageLabelKeyboardHandler
from events.keyboard_state_service import KeyboardStateService


class _KeyEvent:
    def __init__(self, key):
        self._key = key
        self.accepted = False

    def key(self):
        return self._key

    def modifiers(self):
        return Qt.KeyboardModifier.NoModifier

    def isAutoRepeat(self):
        return False

    def accept(self):
        self.accepted = True


class _InputSession:
    def __init__(self):
        self.active: set[str] = set()
        self.calls: list[tuple[str, str]] = []

    def activate(self, owner: str):
        self.calls.append(("activate", owner))
        self.active.add(owner)

    def deactivate(self, owner: str):
        self.calls.append(("deactivate", owner))
        self.active.discard(owner)


def _store(*, overlay_enabled: bool):
    return SimpleNamespace(
        emit_count=0,
        emit_viewport_change=lambda *_args, **_kwargs: None,
        viewport=SimpleNamespace(
            view_state=SimpleNamespace(overlay_enabled=overlay_enabled),
            interaction_state=SimpleNamespace(
                pressed_keys=set(),
                space_bar_pressed=False,
                last_horizontal_movement_key=None,
                last_vertical_movement_key=None,
                last_spacing_movement_key=None,
            ),
        ),
    )


def _image_keyboard(store, session):
    return ImageLabelKeyboardHandler(
        SimpleNamespace(
            store=store,
            keyboard_state_service=KeyboardStateService(store),
            event_bus=None,
            preview=SimpleNamespace(
                is_active=False,
                log_preview_debug=lambda *_args, **_kwargs: None,
                restore=lambda: None,
            ),
            input_session=session,
        )
    )


def test_canvas_wasdqe_press_activates_keyboard_owner_even_when_overlay_disabled():
    store = _store(overlay_enabled=False)
    session = _InputSession()
    keyboard = _image_keyboard(store, session)

    keyboard.handle_key_press(_KeyEvent(Qt.Key.Key_W))

    assert KEYBOARD_MOVE_OWNER in session.active
    assert session.calls == [("activate", KEYBOARD_MOVE_OWNER)]


def test_canvas_wasdqe_release_deactivates_keyboard_owner_even_when_overlay_disabled():
    store = _store(overlay_enabled=True)
    session = _InputSession()
    keyboard = _image_keyboard(store, session)

    keyboard.handle_key_press(_KeyEvent(Qt.Key.Key_W))
    store.viewport.view_state.overlay_enabled = False
    keyboard.handle_key_release(_KeyEvent(Qt.Key.Key_W))

    assert KEYBOARD_MOVE_OWNER not in session.active
    assert session.calls == [
        ("activate", KEYBOARD_MOVE_OWNER),
        ("deactivate", KEYBOARD_MOVE_OWNER),
    ]


def test_canvas_keyboard_owner_stays_active_until_last_wasdqe_release():
    store = _store(overlay_enabled=True)
    session = _InputSession()
    keyboard = _image_keyboard(store, session)

    keyboard.handle_key_press(_KeyEvent(Qt.Key.Key_A))
    keyboard.handle_key_press(_KeyEvent(Qt.Key.Key_D))
    keyboard.handle_key_release(_KeyEvent(Qt.Key.Key_D))

    assert KEYBOARD_MOVE_OWNER in session.active

    keyboard.handle_key_release(_KeyEvent(Qt.Key.Key_A))

    assert KEYBOARD_MOVE_OWNER not in session.active


def test_global_wasdqe_release_stops_movement_after_overlay_is_disabled():
    store = _store(overlay_enabled=True)
    store.invalidate_render_cache = lambda: None
    movement_calls: list[str] = []
    movement = SimpleNamespace(
        start=lambda: movement_calls.append("start"),
        stop=lambda: movement_calls.append("stop"),
    )
    keyboard = GlobalKeyboardHandler(
        store,
        presenter_provider=lambda: None,
        movement_controller=movement,
        keyboard_state=KeyboardStateService(store),
    )

    keyboard.handle_key_press(_KeyEvent(Qt.Key.Key_W))
    store.viewport.view_state.overlay_enabled = False
    keyboard.handle_key_release(_KeyEvent(Qt.Key.Key_W))

    assert movement_calls == ["start", "stop"]
