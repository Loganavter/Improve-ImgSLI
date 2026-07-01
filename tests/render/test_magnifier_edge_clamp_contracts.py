"""Magnifier capture clamp stays stable across viewport zoom changes.

Dogma source: docs/dev/CANVAS_FEATURES.md §Canvas features.
"""

from __future__ import annotations

from types import SimpleNamespace

from domain.types import Point, Rect
from tabs.image_compare.canvas.features.magnifier.feature import build_magnifier_object
from tabs.image_compare.canvas.features.magnifier.models import MagnifierModel
from ui.canvas_infra.scene.context import CanvasSceneBuildContext

def _edge_object():
    model = MagnifierModel(
        id="m1",
        visible=True,
        visible_left=True,
        visible_center=False,
        visible_right=False,
        position=Point(0.0, 0.5),
        offset_relative=Point(0.0, 0.0),
        size_relative=0.2,
        capture_size_relative=0.1,
    )
    store = SimpleNamespace(
        viewport=SimpleNamespace(
            view_state=SimpleNamespace(diff_mode="off"),
            interaction_state=SimpleNamespace(
                is_interactive_mode=False,
                optimize_interactive_movement=False,
            ),
        )
    )
    context = CanvasSceneBuildContext(
        store=store,
        image_label=object(),
        bounds=Rect(0, 0, 1000, 1000),
        label_width=1000,
        label_height=1000,
        pix_w=1000,
        pix_h=1000,
    )
    return build_magnifier_object(
        context=context,
        model=model,
        z_index=0,
        is_active=True,
    )

def test_capture_edge_clamp_does_not_depend_on_zoom(monkeypatch):
    """Zooming must not nudge a capture area that is clamped to an image edge."""
    import tabs.image_compare.canvas.features.magnifier.feature as feature

    monkeypatch.setattr(feature, "get_zoom_level", lambda _widget: 1.0, raising=False)
    zoom_1 = _edge_object()

    monkeypatch.setattr(feature, "get_zoom_level", lambda _widget: 2.0, raising=False)
    zoom_2 = _edge_object()

    assert zoom_1.capture_center is not None
    assert zoom_2.capture_center is not None
    assert zoom_2.capture_center.x == zoom_1.capture_center.x
    assert zoom_2.capture_radius == zoom_1.capture_radius
    assert zoom_1.capture_center.x == zoom_1.capture_radius

def test_capture_edge_clamp_has_no_stroke_margin_gap():
    """Capture geometry may touch image bounds; stroke AA is render clipping."""
    obj = _edge_object()

    assert obj.capture_center is not None
    assert obj.capture_center.x == obj.capture_radius
