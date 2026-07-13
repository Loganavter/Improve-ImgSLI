"""QRhi render pass dogma.

  * each feature's render passes must declare ``stack_role``
  * no hardcoded ``layer=<int>`` / ``priority=<int>`` (use stack_role via
    ``CanvasStackRole``)
  * no feature-named files under ``shader_sources/`` (feature shaders live in
    the feature's own package)

Dogma source: docs/dev/QRHI_CANVAS_FEATURES.md (render pass section + anti-patterns).

NB: tests/runtime/test_stacking_policy.py already covers the *runtime* side of
this (``TestFeatureRenderPassesUseStackRole``); these tests are the *static* check.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from ._framework import (
    SHADER_SOURCES,
    list_all_canvas_features,
    read,
    rel,
)

FEATURES_WITH_PASSES = [
    f for f in list_all_canvas_features() if (f / "passes.py").exists()
]
PASS_IDS = [f.name for f in FEATURES_WITH_PASSES]

_HARDCODED_LAYER_RE = re.compile(r"^\s*(layer|priority)\s*=\s*\d+", re.MULTILINE)

def _local_pass_modules(feature: Path, path: Path, seen: set[Path]) -> None:
    """Follow ``from .sibling import ...`` one level to find split-out pass modules.

    A feature's render-pass classes don't have to live directly in
    ``passes.py`` — see magnifier's ``arc_passes.py``/``magnifier_pass.py``
    split — so this walks ``passes.py``'s own relative imports rather than
    scanning the whole feature package (which would also catch unrelated
    ``layer=``/``priority=`` uses, e.g. gesture bindings' own ``priority=``
    or a scene-build helper's ``stack_hint(layer=...)`` call).
    """
    if path in seen or not path.is_file():
        return
    seen.add(path)
    try:
        tree = ast.parse(read(path))
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.level < 1 or not node.module:
            continue
        parts = node.module.split(".")
        sibling = feature.joinpath(*parts[:-1], f"{parts[-1]}.py")
        if sibling.exists():
            _local_pass_modules(feature, sibling, seen)

def _pass_module_paths(feature: Path) -> list[Path]:
    seen: set[Path] = set()
    _local_pass_modules(feature, feature / "passes.py", seen)
    return sorted(seen)

@pytest.mark.parametrize("feature", FEATURES_WITH_PASSES, ids=PASS_IDS)
def test_render_passes_declare_stack_role(feature):
    paths = _pass_module_paths(feature)
    combined = "\n".join(read(p) for p in paths)
    assert re.search(r"\bstack_role\s*=", combined), (
        f"'{feature.name}' must declare stack_role somewhere in its package "
        f"(do not hardcode layer/priority)"
    )

@pytest.mark.parametrize("feature", FEATURES_WITH_PASSES, ids=PASS_IDS)
def test_render_passes_no_hardcoded_layer_or_priority(feature):
    hits = []
    for path in _pass_module_paths(feature):
        src = read(path)
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
        f"in the feature's own package: {unexpected}"
    )
