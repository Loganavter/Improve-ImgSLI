"""Layout contract: ``NormalizedBounds.union`` math, feature layout-requirement
commands return valid bounds (or None), and an empty feature set yields the
unit canvas layout.

Dogma source: docs/dev/QRHI_CANVAS_FEATURES.md §Canvas Layout Contract.
"""

from __future__ import annotations

from core.store import Store
from shared.rendering.layout_contract import (
    FeatureLayoutRequirement,
    NormalizedBounds,
    VirtualCanvasLayout,
    resolve_virtual_canvas_layout,
)
from ui.canvas_infra.scene.registry import get_canvas_registry
import tabs.image_compare.canvas.features as image_compare_features

get_canvas_registry("image_compare").register_package(image_compare_features)


def get_canvas_feature_commands_by_id(command_id):
    return get_canvas_registry("image_compare").get_feature_commands_by_id(command_id)

def test_normalized_bounds_union_expands_outside_unit_box():
    """QRHI_CANVAS_FEATURES.md: VirtualCanvasLayout uses normalized bounds union."""
    bounds = NormalizedBounds.unit().union(
        NormalizedBounds(x_min=-0.25, x_max=1.5, y_min=0.1, y_max=1.2)
    )

    assert bounds == NormalizedBounds(x_min=-0.25, x_max=1.5, y_min=0.0, y_max=1.2)

def test_layout_requirement_commands_return_valid_bounds_or_none():
    """QRHI_CANVAS_FEATURES.md: render.layout_requirement returns FeatureLayoutRequirement."""
    commands = get_canvas_feature_commands_by_id("render.layout_requirement")
    assert commands

    store = Store()
    for command in commands:
        requirement = command(store, drawing_width=640, drawing_height=480)
        if requirement is None:
            continue
        assert isinstance(requirement, FeatureLayoutRequirement)
        assert requirement.feature_id
        assert requirement.bounds.x_min <= requirement.bounds.x_max
        assert requirement.bounds.y_min <= requirement.bounds.y_max

def test_virtual_canvas_layout_defaults_to_unit_when_no_requirements():
    """QRHI_CANVAS_FEATURES.md: no feature requirements means base 0..1 canvas."""
    layout = resolve_virtual_canvas_layout(())

    assert isinstance(layout, VirtualCanvasLayout)
    assert layout.canvas_bounds == NormalizedBounds.unit()
    assert layout.content_bounds == NormalizedBounds.unit()
    assert layout.resolve_padding_pixels(base_width=100, base_height=50) == (0, 0, 0, 0)
