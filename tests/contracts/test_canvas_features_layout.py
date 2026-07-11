"""Canvas feature placement dogma.

  * feature-specific helpers must NOT live under ``canvas_presentation/``
  * the legacy ``RenderingPipeline`` must not be reintroduced inside features

Dogma source: docs/dev/QRHI_CANVAS_FEATURES.md (anti-patterns +
"Feature geometry belongs to the feature").
"""

from __future__ import annotations

import pytest

from ._framework import (
    CANVAS_PRESENTATION,
    feature_name,
    iter_py,
    list_canvas_features,
    read,
    rel,
)

_NEUTRAL_STEMS = {
    "plan", "models", "plan_builder", "plan_applicator", "render_arch",
    "layout", "gl_surface",
}

def test_canvas_presentation_has_no_feature_named_helpers():
    if not CANVAS_PRESENTATION.is_dir():
        pytest.skip("canvas_presentation/ not present")
    feature_names = {
        feature_name(f) for f in list_canvas_features() if feature_name(f)
    }
    leaks: list[str] = []
    for py in iter_py(CANVAS_PRESENTATION):
        stem = py.stem.lower()
        if stem in _NEUTRAL_STEMS:
            continue
        for fname in feature_names:
            if fname and fname.lower() in stem:
                leaks.append(
                    f"{rel(py)} references feature '{fname}' by name"
                )
    assert not leaks, "\n  - " + "\n  - ".join(leaks)

FEATURES = list_canvas_features()
FEATURE_IDS = [f.name for f in FEATURES]

@pytest.mark.parametrize("feature", FEATURES, ids=FEATURE_IDS)
def test_feature_does_not_reintroduce_rendering_pipeline(feature):
    hits: list[str] = []
    for py in iter_py(feature):
        text = read(py)
        if "RenderingPipeline" not in text:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if "RenderingPipeline" in line and not line.strip().startswith("#"):
                hits.append(f"{rel(py)}:{i}")
                break
    assert not hits, (
        f"'{feature.name}' references RenderingPipeline (forbidden):\n  - "
        + "\n  - ".join(hits)
    )
