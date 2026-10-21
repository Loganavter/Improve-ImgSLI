"""Shift+Space preview: end it on release, and do not tie it to the click point.

Two owner-reported defects (2026-10-22), both measured on a live instance:

1. After releasing `Shift`+`Space` the preview stayed on screen — the gesture
   *begins* on a canvas click, but once the tab shell owns the keyboard focus
   the matching RELEASE is delivered to the global handler, which restored
   nothing (the canvas path did, so the old behaviour only held while the
   canvas actually received the keys).
2. The gesture only matched when the click landed *on* the loupe
   (`_point_in_overlay`): a preview of one side should not depend on where the
   pointer happened to be.
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent


class _Preview:
    def __init__(self, active: bool = True):
        self.is_active = active
        self.restores = 0

    def restore(self):
        self.restores += 1
        self.is_active = False


class _Interaction:
    space_bar_pressed = True
    pressed_keys: set = set()


class _ViewState:
    showing_single_image_mode = 0


class _Viewport:
    def __init__(self):
        self.interaction_state = _Interaction()
        self.view_state = _ViewState()


class _Store:
    def __init__(self):
        self.viewport = _Viewport()
        self.emits: list[str] = []

    def emit_viewport_change(self, scope=""):
        self.emits.append(scope)


class _KeyboardState:
    def release(self, key, is_auto_repeat=False):
        return SimpleNamespace(applied=True, reason="released")


class _Movement:
    def stop(self):
        pass


def _handler(preview):
    from events.app_event.keyboard import GlobalKeyboardHandler

    store = _Store()
    presenter = SimpleNamespace(
        image_label_handler=SimpleNamespace(preview=preview),
    )
    return GlobalKeyboardHandler(
        store,
        presenter_provider=lambda: presenter,
        movement_controller=_Movement(),
        keyboard_state=_KeyboardState(),
    )


def _release(key):
    return QKeyEvent(QEvent.Type.KeyRelease, key, Qt.KeyboardModifier.NoModifier)


def test_space_release_restores_an_active_preview():
    preview = _Preview()
    handler = _handler(preview)
    handler.handle_key_release(_release(Qt.Key.Key_Space))
    assert preview.restores == 1


def test_shift_release_restores_an_active_preview():
    preview = _Preview()
    handler = _handler(preview)
    handler.handle_key_release(_release(Qt.Key.Key_Shift))
    assert preview.restores == 1


def test_release_without_an_active_preview_is_a_no_op():
    preview = _Preview(active=False)
    handler = _handler(preview)
    handler.handle_key_release(_release(Qt.Key.Key_Space))
    handler.handle_key_release(_release(Qt.Key.Key_Shift))
    assert preview.restores == 0


def test_side_preview_matches_anywhere_on_the_canvas(monkeypatch):
    import tabs.image_compare.canvas.features.magnifier.input.gestures as gestures

    for name, value in (
        ("_space_pressed", lambda store: True),
        ("_shift_pressed", lambda ctx: True),
        ("_overlay_enabled", lambda store: True),
        ("_active_combined", lambda store: True),
        ("_has_both_sides_visible", lambda store: True),
        # The pointer is NOT on the loupe: the gesture must still match.
        ("_point_in_overlay", lambda ctx: False),
    ):
        monkeypatch.setattr(gestures, name, value)
    ctx = SimpleNamespace(
        store=object(), handler=object(), local_pos=(0.0, 0.0), button=1, modifiers=0
    )
    assert gestures._matches_side_preview(ctx) is True


def test_side_preview_still_requires_shift(monkeypatch):
    import tabs.image_compare.canvas.features.magnifier.input.gestures as gestures

    for name, value in (
        ("_space_pressed", lambda store: True),
        ("_shift_pressed", lambda ctx: False),
        ("_overlay_enabled", lambda store: True),
        ("_active_combined", lambda store: True),
        ("_has_both_sides_visible", lambda store: True),
        ("_point_in_overlay", lambda ctx: True),
    ):
        monkeypatch.setattr(gestures, name, value)
    ctx = SimpleNamespace(
        store=object(), handler=object(), local_pos=(0.0, 0.0), button=1, modifiers=0
    )
    assert gestures._matches_side_preview(ctx) is False
