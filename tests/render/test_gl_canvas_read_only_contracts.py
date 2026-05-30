"""Read-only GLCanvas previews must not let viewport input mutate the scene."""

from __future__ import annotations

from types import SimpleNamespace

from PyQt6.QtCore import Qt

from ui.canvas_infra.viewport.state import (
    get_pan_offset_x,
    get_pan_offset_y,
    get_zoom_level,
    set_pan_offsets,
    set_zoom_level,
)
from ui.widgets.gl_canvas.interaction import (
    handle_mouse_move_event,
    handle_mouse_press_event,
    handle_wheel_event,
    set_pan,
    set_zoom,
)
from ui.widgets.gl_canvas.render_config import update_display_split_position
from ui.widgets.gl_canvas.state import GLCanvasRuntimeState

class _AcceptedEvent:
    def __init__(self):
        self.accepted = False

    def accept(self):
        self.accepted = True

class _WheelEvent(_AcceptedEvent):
    def modifiers(self):
        return Qt.KeyboardModifier.ControlModifier

    def position(self):
        return SimpleNamespace(x=lambda: 40.0, y=lambda: 30.0)

    def angleDelta(self):
        return SimpleNamespace(y=lambda: 120)

class _MouseEvent(_AcceptedEvent):
    def button(self):
        return Qt.MouseButton.MiddleButton

    def position(self):
        return SimpleNamespace(x=lambda: 20.0, y=lambda: 10.0)

def _canvas():
    return SimpleNamespace(
        runtime_state=GLCanvasRuntimeState(_read_only=True),
        width=lambda: 100,
        height=lambda: 80,
        update=lambda: None,
        zoomChanged=SimpleNamespace(emit=lambda *_args: None),
        _pan_dragging=False,
        _pan_last_pos=SimpleNamespace(x=lambda: 0.0, y=lambda: 0.0),
    )

def test_read_only_canvas_rejects_programmatic_zoom_and_pan():
    canvas = _canvas()
    set_zoom_level(canvas, 3.0)
    set_pan_offsets(canvas, 0.2, -0.1)

    set_zoom(canvas, 5.0)
    set_pan(canvas, 0.4, 0.3)

    assert get_zoom_level(canvas) == 3.0
    assert get_pan_offset_x(canvas) == 0.2
    assert get_pan_offset_y(canvas) == -0.1

def test_read_only_canvas_accepts_and_ignores_viewport_input():
    canvas = _canvas()
    set_zoom_level(canvas, 3.0)
    set_pan_offsets(canvas, 0.2, -0.1)

    wheel = _WheelEvent()
    press = _MouseEvent()
    move = _MouseEvent()
    handle_wheel_event(canvas, wheel)
    handle_mouse_press_event(canvas, press)
    handle_mouse_move_event(canvas, move)

    assert wheel.accepted is True
    assert press.accepted is True
    assert move.accepted is True
    assert get_zoom_level(canvas) == 3.0
    assert get_pan_offset_x(canvas) == 0.2
    assert get_pan_offset_y(canvas) == -0.1
    assert canvas._pan_dragging is False

def test_preview_split_display_ignores_viewport_camera():
    canvas = _canvas()
    canvas.runtime_state._stored_pil_images = [SimpleNamespace(width=100, height=50), None]
    canvas.runtime_state._content_rect_px = (10, 0, 80, 80)
    set_zoom_level(canvas, 8.0)
    set_pan_offsets(canvas, 0.2, 0.0)

    split = update_display_split_position(
        canvas,
        scene=SimpleNamespace(split_position_visual=0.5, is_horizontal=False),
        zoom_level=get_zoom_level(canvas),
        pan_offset_x=get_pan_offset_x(canvas),
        pan_offset_y=get_pan_offset_y(canvas),
        anchor_to_viewport=False,
    )

    assert split == 0.5
