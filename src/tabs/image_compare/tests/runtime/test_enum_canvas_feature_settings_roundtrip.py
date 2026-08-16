"""Enum-kind canvas-feature settings survive the full serialization roundtrip.

The generic sweep (``tests/plugins/test_settings_full_pass.py``) only
exercises DEFAULTS for enum-kind properties — ``CanvasFeatureProperty``
declares no options, so the sweep has no non-default enum value to write.
The two enum properties (``lasers.smoothing.interpolation_method`` and
``filename_overlay.placement_mode``) persist option-id strings
(``"BILINEAR"``/``"edges"`` defaults); this test pins that a non-default
option id survives ``write -> serialize -> deserialize -> read`` and that
the raw value stored in QSettings format is exactly the option id.

Dogma source: docs/dev/CONTRACTS.md §CanvasFeatureProperty / §Settings
persistence contract.
"""

from __future__ import annotations

from core.store_viewport import ViewportState
from ui.canvas_infra.scene.property_access import (
    deserialize_canvas_feature_setting,
    read_canvas_feature_property,
    serialize_canvas_feature_setting,
    write_canvas_feature_property,
)
from ui.canvas_infra.scene.registry import get_canvas_registry
import tabs.image_compare.canvas.features as image_compare_features

_registry = get_canvas_registry("image_compare")
_registry.register_package(image_compare_features)

#: Non-default option ids per enum property, straight from the feature
#: manifests (interpolation method options in
#: canvas/features/magnifier/geometry/layout_plan.py; text placement modes
#: "edges" | "split_line" in ui/canvas_presentation/filename_labels.py).
_ENUM_OPTIONS = {
    "lasers.smoothing.interpolation_method": "LANCZOS",
    "filename_overlay.placement_mode": "split_line",
}


def _property_by_id(prop_id: str):
    for prop in _registry.get_feature_properties():
        if prop.id == prop_id:
            return prop
    raise AssertionError(f"enum property {prop_id!r} not found in the registry")


def test_enum_canvas_feature_settings_roundtrip_non_default_option_id():
    """A non-default enum option id survives write -> serialize -> reload.

    Each enum property must persist its option-id string (not a derived
    number) and restore it into a fresh ViewportState on load.
    """
    for prop_id, option in _ENUM_OPTIONS.items():
        prop = _property_by_id(prop_id)
        assert prop.kind == "enum", f"{prop_id} expected enum kind"
        assert prop.setting_key, f"{prop_id} must declare a setting_key"

        default = read_canvas_feature_property(ViewportState(), prop)["value"]
        assert default != option, (
            f"{prop_id}: {option!r} must be a non-default option "
            f"(default is {default!r})"
        )

        source = ViewportState()
        write_canvas_feature_property(source, prop, {"value": option})
        raw = serialize_canvas_feature_setting(
            prop, read_canvas_feature_property(source, prop)
        )

        # The raw value stored in QSettings format is the option id itself.
        assert raw == option, (
            f"{prop_id}: raw persisted value must be the option id, "
            f"got {raw!r}"
        )

        reloaded = ViewportState()
        write_canvas_feature_property(
            reloaded, prop, deserialize_canvas_feature_setting(prop, raw)
        )
        got = read_canvas_feature_property(reloaded, prop)["value"]
        assert got == option, (
            f"{prop_id}: option {option!r} drifted across reload, got {got!r}"
        )
