"""apply_canvas_render_plan resolves composition trees and stashes them
on the canvas — the unified API entry point for both workspaces."""

from __future__ import annotations

from types import SimpleNamespace

from PIL import Image
from PySide6.QtGui import QColor

from ui.canvas_presentation.composition import (
    LayerNode,
    SplitNode,
)
from ui.canvas_presentation.plan import CanvasRenderPlan
from ui.canvas_presentation.plan_applicator import apply_canvas_render_plan


def _legacy_plan(composition_root=None) -> CanvasRenderPlan:
    """Build a minimal CanvasRenderPlan suitable for composition routing.

    Legacy 2-image fields are filled with placeholders; when composition_root
    is set, the applicator should ignore them and route through the
    composition handler.
    """
    return CanvasRenderPlan(
        image1=None,
        image2=None,
        source_image1=None,
        source_image2=None,
        source_key=(),
        canvas_w=400,
        canvas_h=200,
        render_scene=None,
        overlay_layout=None,
        capture_visible=False,
        capture_color=QColor(0, 0, 0, 0),
        guides_enabled=False,
        guides_color=QColor(0, 0, 0, 0),
        guides_thickness=0,
        composition_root=composition_root,
    )


def test_composition_plan_resolved_and_stashed_on_canvas():
    canvas = SimpleNamespace()
    root = SplitNode(
        direction="h",
        children=(
            LayerNode(layer_id=1, image=Image.new("RGBA", (10, 10))),
            LayerNode(layer_id=2, image=Image.new("RGBA", (10, 10))),
        ),
        weights=(1.0, 1.0),
    )
    plan = _legacy_plan(composition_root=root)

    apply_canvas_render_plan(canvas, plan)

    assert canvas._active_render_plan is plan
    resolved = canvas._active_composition
    assert resolved.canvas_w == 400
    assert resolved.canvas_h == 200
    assert len(resolved.layers) == 2
    assert resolved.layers[0].rect == (0, 0, 200, 200)
    assert resolved.layers[1].rect == (200, 0, 200, 200)


def test_composition_routing_skips_legacy_image_pipeline():
    """When composition_root is set, the applicator must not touch
    base_images / overlay_layout / split-position machinery — those fields
    are placeholders. Verified by checking no legacy attributes ended up
    on the canvas."""
    canvas = SimpleNamespace()
    plan = _legacy_plan(
        composition_root=LayerNode(layer_id=1, image=Image.new("RGBA", (10, 10))),
    )

    apply_canvas_render_plan(canvas, plan)

    # The composition handler only sets these two:
    assert hasattr(canvas, "_active_composition")
    assert hasattr(canvas, "_active_render_plan")
    # Legacy attributes the 2-image path would set were never touched:
    assert not hasattr(canvas, "_clip_overlays_to_content_rect")
    assert not hasattr(canvas, "_store")


def test_composition_resolved_picks_up_fill_rgba_from_plan():
    canvas = SimpleNamespace()
    plan = CanvasRenderPlan(
        image1=None, image2=None,
        source_image1=None, source_image2=None,
        source_key=(),
        canvas_w=10, canvas_h=10,
        render_scene=None, overlay_layout=None,
        capture_visible=False, capture_color=QColor(0, 0, 0, 0),
        guides_enabled=False, guides_color=QColor(0, 0, 0, 0),
        guides_thickness=0,
        fill_rgba=(20, 20, 20, 255),
        composition_root=LayerNode(layer_id=1, image=Image.new("RGBA", (10, 10))),
    )
    apply_canvas_render_plan(canvas, plan)
    assert canvas._active_composition.fill_rgba == (20, 20, 20, 255)
