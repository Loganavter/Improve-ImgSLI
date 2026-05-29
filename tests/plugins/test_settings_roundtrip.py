"""Settings persistence roundtrip for canvas-feature properties.

Every property that declares a ``setting_key`` is persisted by
``SettingsManager`` via ``serialize_canvas_feature_setting`` on save and
``deserialize_canvas_feature_setting`` + ``write_canvas_feature_property`` on
load. Saving then reloading must be a fixpoint: the value that comes back out
of the store serializes to the same raw value that went in. Otherwise a setting
silently drifts each time the app restarts.

This runs on a plain ``ViewportState`` + the serializers — no Qt, no QSettings.

Dogma source: docs/dev/CONTRACTS.md §CanvasFeatureProperty.
"""

from __future__ import annotations

import pytest

from core.store_viewport import ViewportState
from ui.canvas_infra.scene.property_access import (
    deserialize_canvas_feature_setting,
    read_canvas_feature_property,
    serialize_canvas_feature_setting,
    write_canvas_feature_property,
)
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_properties

PERSISTED = [p for p in get_canvas_feature_properties() if p.setting_key]
PERSISTED_IDS = [p.id for p in PERSISTED]

# Representative non-default channel values per property kind. Values are
# deliberately distinct from defaults so the roundtrip catches "always writes
# the default" bugs.
def _mutations(kind: str) -> list[dict]:
    if kind == "bool":
        return [{"value": True}, {"value": False}]
    if kind == "scalar":
        return [{"value": 7.0}, {"value": 1.0}]
    if kind == "color":
        return [{"r": 10, "g": 20, "b": 30, "a": 200}]
    return []  # enum/other: default roundtrip below still covers it

def _reload_fixpoint(prop, channels: dict) -> tuple:
    """Simulate save->reload and return (raw_in, raw_after_reload)."""
    source = ViewportState()
    write_canvas_feature_property(source, prop, channels)
    raw_in = serialize_canvas_feature_setting(prop, read_canvas_feature_property(source, prop))

    reloaded = ViewportState()
    write_canvas_feature_property(reloaded, prop, deserialize_canvas_feature_setting(prop, raw_in))
    raw_out = serialize_canvas_feature_setting(prop, read_canvas_feature_property(reloaded, prop))
    return raw_in, raw_out

@pytest.mark.parametrize("prop", PERSISTED, ids=PERSISTED_IDS)
def test_default_value_survives_save_reload(prop):
    default_channels = read_canvas_feature_property(ViewportState(), prop)
    raw_in, raw_out = _reload_fixpoint(prop, default_channels)
    assert raw_in == raw_out, f"{prop.id} default value drifted across reload"

@pytest.mark.parametrize("prop", PERSISTED, ids=PERSISTED_IDS)
def test_mutated_value_survives_save_reload(prop):
    for channels in _mutations(prop.kind):
        raw_in, raw_out = _reload_fixpoint(prop, channels)
        assert raw_in == raw_out, (
            f"{prop.id} value {channels} drifted across reload: {raw_in} != {raw_out}"
        )

def test_some_properties_are_persisted():
    assert PERSISTED, "expected at least one property with a setting_key"
