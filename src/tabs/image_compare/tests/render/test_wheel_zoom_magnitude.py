"""Wheel-zoom must apply every tick immediately and scale by delta magnitude.

docs/dev/rendering/tile-array-atlas-plan.md Findings: a "render pending,
drop this tick" throttle used to sit in front of every wheel-zoom tick to
protect a slow render from an OS-buffered burst of wheel deltas. It only
moved the problem -- dropped ticks lost their direction and magnitude,
which is what let zoom visibly reverse or stall on a fast burst. The
throttle (shared/rendering/zoom_coordinator.py) has been removed outright:
Qt's own widget.update() already coalesces into one repaint no matter how
many times it's called before the next frame, so there was nothing left
for a custom throttle to protect. Every wheel tick, including a rapid
back-to-back burst, must now update zoom/pan unconditionally.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt

from tabs.image_compare.canvas.interaction import handle_wheel_event
from tabs.image_compare.canvas.state import CanvasRuntimeState
from ui.canvas_infra.viewport.contract import WheelZoomRequest
from ui.canvas_infra.viewport.state import get_zoom_level, set_pan_offsets, set_zoom_level
from ui.canvas_infra.viewport.zoom import compute_zoom_wheel_transform


class _WheelEvent:
    def __init__(self, angle_delta_y: int):
        self._angle_delta_y = angle_delta_y
        self.accepted = False

    def accept(self):
        self.accepted = True

    def modifiers(self):
        return Qt.KeyboardModifier.ControlModifier

    def position(self):
        return SimpleNamespace(x=lambda: 40.0, y=lambda: 30.0)

    def angleDelta(self):
        return SimpleNamespace(y=lambda: self._angle_delta_y)


def _canvas():
    return SimpleNamespace(
        runtime_state=CanvasRuntimeState(),
        width=lambda: 100,
        height=lambda: 80,
        update=lambda: None,
        zoomChanged=SimpleNamespace(emit=lambda *_args: None),
    )


def test_every_tick_in_a_rapid_burst_is_applied_no_throttle():
    canvas = _canvas()
    set_zoom_level(canvas, 10.0)
    set_pan_offsets(canvas, 0.0, 0.0)

    zooms = []
    for _ in range(5):
        handle_wheel_event(canvas, _WheelEvent(120))
        zooms.append(get_zoom_level(canvas))

    # Every tick moved zoom -- strictly increasing, none dropped.
    assert zooms == sorted(zooms)
    assert len(set(zooms)) == len(zooms)


def _request(angle_delta_y: int, current_zoom: float = 10.0) -> WheelZoomRequest:
    return WheelZoomRequest(
        widget_width=100,
        widget_height=100,
        mouse_x=50.0,
        mouse_y=50.0,
        current_zoom=current_zoom,
        current_pan_x=0.0,
        current_pan_y=0.0,
        angle_delta_y=angle_delta_y,
    )


def test_zoom_factor_scales_with_delta_magnitude_not_just_sign():
    """A coalesced burst worth 2 notches (240 units) must compound to the
    same total zoom change as two separate single-notch (120 units) events
    -- not the same fixed step as one single notch."""
    one_notch = compute_zoom_wheel_transform(_request(120))
    two_notches = compute_zoom_wheel_transform(_request(240))
    assert one_notch is not None and two_notches is not None
    one_notch_zoom = one_notch[0]
    two_notch_zoom = two_notches[0]

    twice_applied = compute_zoom_wheel_transform(
        _request(120, current_zoom=one_notch_zoom)
    )
    assert twice_applied is not None
    assert two_notch_zoom == pytest.approx(twice_applied[0])
    assert two_notch_zoom > one_notch_zoom
