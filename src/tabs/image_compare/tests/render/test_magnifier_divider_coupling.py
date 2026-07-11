"""Magnifier combines at the spacing threshold and separates above it — the
coupling between divider proximity and magnifier combine state.

Dogma source: docs/dev/CONTRACTS.md §OverlayMovementHandler.
"""

from __future__ import annotations

from types import SimpleNamespace

from domain.types import Point, Rect
from tabs.image_compare.canvas.features.magnifier.constants import (
    MIN_MAGNIFIER_SPACING_RELATIVE_FOR_COMBINE,
)
from tabs.image_compare.canvas.features.magnifier.feature import build_magnifier_object
from tabs.image_compare.canvas.features.magnifier.state.models import MagnifierModel
from ui.canvas_infra.scene.context import CanvasSceneBuildContext

def _object_for_spacing(spacing: float):
    model = MagnifierModel(
        id="m1",
        visible=True,
        visible_left=True,
        visible_center=False,
        visible_right=True,
        position=Point(0.5, 0.5),
        offset_relative=Point(0.0, 0.0),
        size_relative=0.2,
        capture_size_relative=0.1,
        spacing_relative=spacing,
        is_horizontal=False,
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
        image_label=None,
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

def test_magnifier_combines_at_spacing_threshold():
    """CONTRACTS.md: OverlayMovementHandler combine state follows spacing threshold."""
    obj = _object_for_spacing(MIN_MAGNIFIER_SPACING_RELATIVE_FOR_COMBINE)

    assert obj.is_combined is True
    assert len(obj.circles) == 1
    assert obj.circles[0].role == "combined"

def test_magnifier_separates_above_spacing_threshold():
    """CONTRACTS.md: OverlayMovementHandler separate mode keeps spacing geometry."""
    spacing = MIN_MAGNIFIER_SPACING_RELATIVE_FOR_COMBINE + 0.05
    obj = _object_for_spacing(spacing)

    assert obj.is_combined is False
    assert [circle.role for circle in obj.circles] == ["left", "right"]

    left, right = obj.circles
    distance = right.center.x - left.center.x
    expected_radius = (0.2 * 1000.0) / 2.0
    expected_distance = (expected_radius * 2.0) + (spacing * 1000.0)
    assert distance == expected_distance
