"""Canvas-feature settings full pass — one sweep over every persisted property.

Replaces the old per-property parametrized roundtrip tests with a single
generic sweep over the whole persisted property surface (divider thickness,
guides, filename overlay, magnifier chrome, …): every property that declares
a ``setting_key`` must survive ``serialize -> write -> read -> deserialize``
as a fixpoint — the raw value that goes into QSettings must be exactly the
value that comes back out, for both defaults and mutated channels.

Dogma source: docs/dev/CONTRACTS.md §Settings persistence contract (the
feature-property half of the full pass). This lives under the tab's own
tests because the root ``tests/`` suite must not import tab internals
(tests/contracts/test_root_tests_no_tab_internals_leak.py).
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

PERSISTED = [p for p in _registry.get_feature_properties() if p.setting_key]


def _mutations(kind: str) -> list[dict]:
    if kind == "bool":
        return [{"value": True}, {"value": False}]
    if kind == "scalar":
        # Boundary values carried over from the old per-property roundtrip
        # test (0..99 range points) — the sweep is its single successor.
        return [{"value": 0.0}, {"value": 1.0}, {"value": 12.0}, {"value": 99.0}]
    if kind == "color":
        return [{"r": 10, "g": 20, "b": 30, "a": 200}]
    return []


def _reload_fixpoint(prop, channels: dict) -> tuple:
    """Simulate save->reload and return (raw_in, raw_after_reload)."""
    source = ViewportState()
    write_canvas_feature_property(source, prop, channels)
    raw_in = serialize_canvas_feature_setting(prop, read_canvas_feature_property(source, prop))

    reloaded = ViewportState()
    write_canvas_feature_property(reloaded, prop, deserialize_canvas_feature_setting(prop, raw_in))
    raw_out = serialize_canvas_feature_setting(prop, read_canvas_feature_property(reloaded, prop))
    return raw_in, raw_out


def test_some_properties_are_persisted():
    assert PERSISTED, "expected at least one property with a setting_key"


def test_every_persisted_property_full_pass_fixpoint():
    """Full pass: every persisted property roundtrips defaults AND mutations.

    Aggregates all failures into one report instead of one test per
    property — the sweep covers the whole surface in a single pass.
    """
    assert PERSISTED, "expected at least one property with a setting_key"
    failures: list[str] = []
    for prop in PERSISTED:
        default_channels = read_canvas_feature_property(ViewportState(), prop)
        raw_in, raw_out = _reload_fixpoint(prop, default_channels)
        if raw_in != raw_out:
            failures.append(
                f"{prop.setting_key} default value drifted across reload: "
                f"{raw_in!r} != {raw_out!r}"
            )
        for channels in _mutations(prop.kind):
            raw_in, raw_out = _reload_fixpoint(prop, channels)
            if raw_in != raw_out:
                failures.append(
                    f"{prop.setting_key} value {channels} drifted across "
                    f"reload: {raw_in!r} != {raw_out!r}"
                )
    assert not failures, (
        "persisted canvas-feature properties that are not a save->load "
        "fixpoint (the declared kind does not match the real roundtrip "
        "format):\n  - " + "\n  - ".join(failures)
    )