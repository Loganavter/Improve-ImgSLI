"""CanvasFeatureProperty channel shapes match the property kind.

The serialization roundtrip half of this file moved to
``tests/plugins/test_settings_full_pass.py`` (the generic sweep over every
persisted property, including the boundary values that used to live here) —
this file keeps the channel-shape dogmas only:
``channels`` describe the keyframe track width per kind (bool/scalar/enum ->
1, color -> 4) and channel ids must be unique.

Dogma source: docs/dev/CONTRACTS.md §CanvasFeatureProperty.
"""

from __future__ import annotations

from ui.canvas_infra.scene.registry import get_canvas_registry
import tabs.image_compare.canvas.features as image_compare_features

_registry = get_canvas_registry("image_compare")
_registry.register_package(image_compare_features)

def get_canvas_feature_properties():
    return _registry.get_feature_properties()

def test_property_channel_shapes_match_property_kind():
    """CONTRACTS.md: CanvasFeatureProperty channels describe keyframe track shape."""
    expected = {
        "bool": 1,
        "scalar": 1,
        "enum": 1,
        "color": 4,
    }

    for prop in get_canvas_feature_properties():
        assert prop.channels, f"{prop.id} has no channels"
        assert len(prop.channels) == expected[prop.kind], (
            f"{prop.id} kind={prop.kind} channels={prop.channels}"
        )
        channel_ids = [channel.id for channel in prop.channels]
        assert len(channel_ids) == len(set(channel_ids)), f"{prop.id} duplicate channels"