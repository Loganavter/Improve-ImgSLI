"""GL pass dogma.

  * each ``gl_passes.py`` must declare ``stack_role``
  * no hardcoded ``layer=<int>`` / ``priority=<int>`` (use stack_role via
    ``CanvasStackRole``)
  * no feature-named files under ``shader_sources/`` (feature shaders live in
    the feature's own ``gl_passes.py``)

Dogma source: docs/dev/CANVAS_FEATURES.md (GL pass section + anti-patterns).

NB: tests/test_stacking_policy.py already covers the *runtime* side of this
(``TestFeatureGLPassesUseStackRole``); these tests are the *static* check.
"""

from __future__ import annotations

import re

import pytest

from ._framework import (
    SHADER_SOURCES,
    list_canvas_features,
    read,
    rel,
)

FEATURES_WITH_GL = [
    f for f in list_canvas_features() if (f / "gl_passes.py").exists()
]
GL_IDS = [f.name for f in FEATURES_WITH_GL]

_HARDCODED_LAYER_RE = re.compile(r"^\s*(layer|priority)\s*=\s*\d+", re.MULTILINE)

@pytest.mark.parametrize("feature", FEATURES_WITH_GL, ids=GL_IDS)
def test_gl_passes_declare_stack_role(feature):
    src = read(feature / "gl_passes.py")
    assert re.search(r"\bstack_role\s*=", src), (
        f"'{feature.name}/gl_passes.py' must declare stack_role (do not "
        f"hardcode layer/priority)"
    )

@pytest.mark.parametrize("feature", FEATURES_WITH_GL, ids=GL_IDS)
def test_gl_passes_no_hardcoded_layer_or_priority(feature):
    path = feature / "gl_passes.py"
    src = read(path)
    hits = []
    for m in _HARDCODED_LAYER_RE.finditer(src):
        line = src[: m.start()].count("\n") + 1
        hits.append(f"{rel(path)}:{line} ({m.group(1)}=<int>)")
    assert not hits, (
        "hardcoded layer/priority — use stack_role:\n  - "
        + "\n  - ".join(hits)
    )

def test_shader_sources_does_not_contain_feature_shaders():
    if not SHADER_SOURCES.is_dir():
        pytest.skip("shader_sources/ not present")
    allowed = {"base.py", "common.py", "__init__.py"}
    unexpected = [
        p.name for p in SHADER_SOURCES.iterdir()
        if p.is_file() and p.name not in allowed
    ]
    assert not unexpected, (
        f"unexpected file(s) under shader_sources/ — feature shaders belong "
        f"in <feature>/gl_passes.py: {unexpected}"
    )
