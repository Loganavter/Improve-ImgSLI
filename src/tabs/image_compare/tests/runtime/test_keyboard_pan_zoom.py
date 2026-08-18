"""Arrow-key pan + `+`/`-` zoom on the Image Compare canvas (fixed chords;
see the keyboard-navigation plan Phase 2).

Checks the applied math at the canvas-interaction level with lightweight
fakes, mirroring the wheel/pan-drag formulas so parity holds.
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import Qt

from tabs.image_compare.canvas import interaction as ic_interaction


class _KeyEvent:
    def __init__(self, key):
        self._key = key
        self.accepted = False

    def key(self):
        return self._key

    def accept(self):
        self.accepted = True


class _ZoomSignal:
    def emit(self, *_args, **_kwargs):
        pass


class _IcRuntimeState:
    _read_only = False
    _render_scene = None
    _split_position_sync = None
    _store = None
    _stored_pil_images = []
    _inner_content_rect_px = None
    _content_rect_px = None


class _IcFakeWidget:
    def __init__(self):
        self.runtime_state = _IcRuntimeState()
        self.zoomChanged = _ZoomSignal()
        self.updated = 0

    def update(self):
        self.updated += 1

    def width(self):
        return 1000

    def height(self):
        return 800


def test_ic_arrow_right_pans_positive_x():
    widget = _IcFakeWidget()
    event = _KeyEvent(Qt.Key.Key_Right)
    ic_interaction.handle_key_press_event(widget, event)
    assert event.accepted
    from ui.canvas_infra.viewport.state import get_pan_offset_x

    assert get_pan_offset_x(widget) == 0.05


def test_ic_arrow_up_pans_negative_y():
    widget = _IcFakeWidget()
    event = _KeyEvent(Qt.Key.Key_Up)
    ic_interaction.handle_key_press_event(widget, event)
    from ui.canvas_infra.viewport.state import get_pan_offset_y

    assert get_pan_offset_y(widget) == -0.05


def test_ic_plus_minus_zoom_in_and_out():
    widget = _IcFakeWidget()
    from ui.canvas_infra.viewport.state import get_zoom_level

    ic_interaction.handle_key_press_event(widget, _KeyEvent(Qt.Key.Key_Plus))
    z1 = get_zoom_level(widget)
    assert z1 > 1.0
    ic_interaction.handle_key_press_event(widget, _KeyEvent(Qt.Key.Key_Minus))
    z2 = get_zoom_level(widget)
    assert z2 < z1
    assert z2 >= 1.0


def test_ic_non_canvas_key_still_emits():
    widget = _IcFakeWidget()
    emitted = []
    widget.keyPressed = SimpleNamespace(emit=lambda event: emitted.append(event))
    event = _KeyEvent(Qt.Key.Key_P)
    ic_interaction.handle_key_press_event(widget, event)
    assert not event.accepted
    assert emitted == [event]
