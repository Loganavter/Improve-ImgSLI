"""Each canvas feature must declare a discoverable WIDGET_FEATURE with a name.

Dogma source: docs/dev/CANVAS_FEATURES.md (Quick Start, Checklist).
"""

from __future__ import annotations

import pytest

from ._framework import feature_name, list_canvas_features, read

FEATURES = list_canvas_features()
FEATURE_IDS = [f.name for f in FEATURES]

@pytest.mark.parametrize("feature", FEATURES, ids=FEATURE_IDS)
def test_feature_exports_widget_feature(feature):
    manifest = feature / "manifest.py"
    widget = feature / "widget.py"
    found = any(
        cand.exists() and "WIDGET_FEATURE" in read(cand)
        for cand in (manifest, widget)
    )
    assert found, (
        f"feature '{feature.name}' must export WIDGET_FEATURE via manifest.py "
        f"or widget.py"
    )

@pytest.mark.parametrize("feature", FEATURES, ids=FEATURE_IDS)
def test_feature_has_name_field(feature):
    name = feature_name(feature)
    assert name is not None, (
        f"feature '{feature.name}' has no name=\"...\" field in widget.py / "
        f"feature.py / manifest.py"
    )
    assert not name.startswith("_"), (
        f"feature name '{name}' must not start with '_' (would be excluded "
        f"from auto-discovery)"
    )

def test_feature_names_are_unique():
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for feature in FEATURES:
        name = feature_name(feature)
        if name is None:
            continue
        if name in seen:
            duplicates.append(
                f"'{name}' in {feature.name} and {seen[name]}"
            )
        else:
            seen[name] = feature.name
    assert not duplicates, "duplicate feature names: " + "; ".join(duplicates)
