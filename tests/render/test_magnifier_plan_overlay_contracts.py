"""Magnifier plan overlays convert through the active image-content rect.

Dogma source: docs/dev/CANVAS_FEATURES.md §Canvas presentation.
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor

from ui.canvas_features.magnifier.plan_overlay import apply_magnifier_plan_overlay
from ui.canvas_presentation.plan import CanvasRenderPlan, OverlayLayout, OverlaySlot

class _Canvas:
    def __init__(self):
        self.runtime_state = SimpleNamespace(
            _content_rect_px=(7, 0, 333, 250),
            _inner_content_rect_px=(10, 0, 300, 250),
            _content_sr=1.0,
            _capture_circles=[],
            _guide_sets=[],
        )
        self.overlay_coords = None
        self.gpu_params = None

    def clear_feature_overlay_gpu(self):
        raise AssertionError("overlay should be applied, not cleared")

    def set_overlay_coords(self, capture_center, capture_radius, overlay_centers, overlay_radius):
        self.overlay_coords = (
            capture_center,
            capture_radius,
            tuple(overlay_centers),
            overlay_radius,
        )

    def set_feature_overlay_gpu_params(self, *args):
        self.gpu_params = args

def _plan(layout):
    return CanvasRenderPlan(
        image1=object(),
        image2=object(),
        source_image1=object(),
        source_image2=object(),
        source_key=("test",),
        canvas_w=1000,
        canvas_h=500,
        gl_scene=SimpleNamespace(overlay_clip_rect=(100, 0, 800, 500)),
        overlay_layout=layout,
        capture_visible=True,
        capture_color=QColor(255, 255, 255),
        guides_enabled=False,
        guides_color=QColor(255, 255, 255),
        guides_thickness=1,
    )

def test_plan_overlay_uses_inner_content_rect_for_converted_geometry():
    """Plan overlay geometry must match scene-builder image-content bounds."""
    layout = OverlayLayout(
        slots=(
            OverlaySlot(
                center=QPointF(500.0, 250.0),
                radius=50.0,
                uv_rect=(0.0, 0.0, 1.0, 1.0),
                uv_rect2=(0.0, 0.0, 1.0, 1.0),
                source=0,
                is_combined=False,
                internal_split=0.5,
                horizontal=False,
                divider_visible=False,
                divider_color=(1.0, 1.0, 1.0, 1.0),
                divider_thickness_uv=0.0,
                border_color=QColor(255, 255, 255),
                border_width=2.0,
            ),
        ),
        capture_center=QPointF(500.0, 250.0),
        capture_radius=50.0,
        overlay_centers=((500.0, 250.0),),
        overlay_radius=50.0,
        border_color=QColor(255, 255, 255),
    )
    canvas = _Canvas()

    apply_magnifier_plan_overlay(canvas, _plan(layout))

    capture_center, capture_radius, overlay_centers, overlay_radius = canvas.overlay_coords
    assert capture_center.x() == 160.0
    assert capture_center.y() == 125.0
    assert capture_radius == 18.75
    assert overlay_centers[0].x() == 160.0
    assert overlay_centers[0].y() == 125.0
    assert overlay_radius == 18.75
