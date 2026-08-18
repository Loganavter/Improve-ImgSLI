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


def test_ic_arrow_pan_matches_pan_drag_formula():
    """An arrow nudge equals a pan-drag over ``nudge_fraction * width`` px."""
    from ui.canvas_infra.viewport.contract import PanDragRequest
    from ui.canvas_infra.viewport.state import get_pan_offset_x
    from ui.canvas_infra.viewport.zoom import compute_zoom_pan_drag_transform

    for zoom in (1.0, 4.0, 0.5):
        widget = _IcFakeWidget()
        ic_interaction.set_zoom_level(widget, zoom)
        ic_interaction.handle_key_press_event(
            widget, _KeyEvent(Qt.Key.Key_Right)
        )
        expected = compute_zoom_pan_drag_transform(
            PanDragRequest(
                widget_width=widget.width(),
                widget_height=widget.height(),
                current_zoom=zoom,
                current_pan_x=0.0,
                current_pan_y=0.0,
                last_mouse_x=0.0,
                last_mouse_y=0.0,
                mouse_x=0.05 * widget.width(),
                mouse_y=0.0,
            )
        )
        assert expected is not None
        assert abs(get_pan_offset_x(widget) - expected[0]) < 1e-9
        assert expected[0] == 0.05 / zoom


def test_ic_center_zoom_keeps_pan_unchanged():
    """Keyboard zoom anchors at the viewport center -> pan stays fixed."""
    import pytest

    from ui.canvas_infra.viewport.state import get_pan_offset_x, get_pan_offset_y

    widget = _IcFakeWidget()
    ic_interaction.set_pan_offsets(widget, 0.25, -0.1)
    before = (get_pan_offset_x(widget), get_pan_offset_y(widget))

    ic_interaction.handle_key_press_event(widget, _KeyEvent(Qt.Key.Key_Plus))
    after = (get_pan_offset_x(widget), get_pan_offset_y(widget))
    assert after == pytest.approx(before, abs=1e-12)

    ic_interaction.handle_key_press_event(widget, _KeyEvent(Qt.Key.Key_Minus))
    after = (get_pan_offset_x(widget), get_pan_offset_y(widget))
    assert after == pytest.approx(before, abs=1e-12)


def test_ic_keyboard_zoom_matches_wheel_at_center():
    """`+` applies exactly the wheel transform for one notch at the center."""
    from ui.canvas_infra.viewport.contract import WheelZoomRequest
    from ui.canvas_infra.viewport.state import get_zoom_level
    from ui.canvas_infra.viewport.zoom import compute_zoom_wheel_transform

    widget = _IcFakeWidget()
    ic_interaction.handle_key_press_event(widget, _KeyEvent(Qt.Key.Key_Plus))
    expected = compute_zoom_wheel_transform(
        WheelZoomRequest(
            widget_width=widget.width(),
            widget_height=widget.height(),
            mouse_x=widget.width() / 2.0,
            mouse_y=widget.height() / 2.0,
            current_zoom=1.0,
            current_pan_x=0.0,
            current_pan_y=0.0,
            angle_delta_y=120,
        )
    )
    assert expected is not None
    assert abs(get_zoom_level(widget) - expected[0]) < 1e-9


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
