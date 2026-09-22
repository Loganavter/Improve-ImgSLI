"""Base-image render-pass manifest dogma (Phase F flag-day).

The Phase-A0 manifest
(``tabs/image_compare/canvas/rhi_renderer/passes.py``) was a stepping
stone: it declared the base-image stage while the engine pass did not
exist yet. The single merged pass now lives in
``src/engine/gpu/base_images_pass.py`` (Phase E2) and both tab-local
copies are retired, so this dogma pins the manifest at its final home:

* ``engine/gpu/base_images_pass.py`` ``BaseImagesPass`` declares
  ``stack_role`` (a ``CanvasStackRole`` member) and ``visibility`` (a
  ``SceneVisibility`` member) -- never hardcoded ``layer=<int>`` /
  ``priority=<int>``.
* role parity with multi_compare's tab-hooks ``BaseImagesPass`` so the
  central stacking policy orders both tabs' base stages identically.
* the old tab manifest module must NOT exist (no second declaration).
* ``renderer.py`` wiring is untouched: feature passes still come from
  ``registry().get_render_passes()``, the draw submit still goes through
  ``submit_array_draw``, and no ``RENDER_PASSES`` is (re)defined there.

Dogma source: docs/dev/CONTRACTS.md (CanvasRenderPass / stacking policy).
"""

from __future__ import annotations

import ast
import re

from ._framework import ROOT, parse, read

ENGINE_PASS = ROOT / "src" / "engine" / "gpu" / "base_images_pass.py"
RETIRED_IC_MANIFEST = (
    ROOT / "src" / "tabs" / "image_compare" / "canvas" / "rhi_renderer" / "passes.py"
)
IC_RENDERER = (
    ROOT / "src" / "tabs" / "image_compare" / "canvas" / "rhi_renderer" / "renderer.py"
)
MC_BASE_IMAGES = (
    ROOT
    / "src"
    / "tabs"
    / "multi_compare"
    / "scene"
    / "passes"
    / "base_images.py"
)

_HARDCODED_LAYER_RE = re.compile(r"^\s*(layer|priority)\s*=\s*\d+", re.MULTILINE)


def _parse(path):
    tree = parse(path)
    if tree is None:
        raise SyntaxError(f"cannot parse {path}")
    return tree


def _class_attr_value(tree: ast.Module, class_name: str, attr: str):
    """Return ``(owner, member)`` for ``attr = Owner.member`` in class body."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for stmt in node.body:
                if (
                    isinstance(stmt, ast.Assign)
                    and len(stmt.targets) == 1
                    and isinstance(stmt.targets[0], ast.Name)
                    and stmt.targets[0].id == attr
                    and isinstance(stmt.value, ast.Attribute)
                    and isinstance(stmt.value.value, ast.Name)
                ):
                    return (stmt.value.value.id, stmt.value.attr)
    return None


def test_tab_manifest_retired():
    assert not RETIRED_IC_MANIFEST.exists(), (
        "tab-local base-image manifest retired in Phase F: "
        "src/tabs/image_compare/canvas/rhi_renderer/passes.py must not "
        "exist (single home: engine/gpu/base_images_pass.py)"
    )


def test_engine_pass_declares_stack_role_and_visibility():
    tree = _parse(ENGINE_PASS)
    role = _class_attr_value(tree, "BaseImagesPass", "stack_role")
    assert role is not None and role[0] == "CanvasStackRole", (
        "engine BaseImagesPass must declare stack_role = "
        "CanvasStackRole.<ROLE> (do not hardcode layer/priority)"
    )
    visibility = _class_attr_value(tree, "BaseImagesPass", "visibility")
    assert visibility is not None and visibility[0] == "SceneVisibility", (
        "engine BaseImagesPass must declare visibility = "
        "SceneVisibility.<SCOPE>"
    )


def test_manifest_role_parity_with_multi_compare():
    """Engine base stage resolves through the same role as MC hooks."""
    mc_tree = _parse(MC_BASE_IMAGES)
    mc_role = _class_attr_value(mc_tree, "BaseImagesPass", "stack_role")
    mc_vis = _class_attr_value(mc_tree, "BaseImagesPass", "visibility")
    assert mc_role is not None and mc_vis is not None, (
        "multi_compare BaseImagesPass must keep its stack_role/visibility "
        "attrs (parity reference)"
    )
    tree = _parse(ENGINE_PASS)
    assert _class_attr_value(tree, "BaseImagesPass", "stack_role") == mc_role, (
        f"engine BaseImagesPass.stack_role must match multi_compare "
        f"BaseImagesPass.stack_role ({mc_role})"
    )
    assert _class_attr_value(tree, "BaseImagesPass", "visibility") == mc_vis, (
        f"engine BaseImagesPass.visibility must match multi_compare "
        f"BaseImagesPass.visibility ({mc_vis})"
    )


def test_manifest_no_hardcoded_layer_or_priority():
    for path in (ENGINE_PASS, IC_RENDERER):
        src = read(path)
        hits = [
            f"{path.name}:{src[: m.start()].count(chr(10)) + 1}"
            for m in _HARDCODED_LAYER_RE.finditer(src)
        ]
        assert not hits, (
            "hardcoded layer/priority -- use stack_role:\n  - "
            + "\n  - ".join(hits)
        )


def test_renderer_wiring_unchanged():
    """Manifest is declaration-only: renderer.py keeps its own wiring."""
    src = read(IC_RENDERER)
    assert "registry().get_render_passes()" in src, (
        "renderer.py must keep wiring feature passes from the registry "
        "(manifest adds a declaration, it does not rewire)"
    )
    assert "submit_array_draw" in src, (
        "renderer.py must keep the base array-draw submit path "
        "(manifest must not change pass order)"
    )
    tree = _parse(IC_RENDERER)
    redefined = [
        node.lineno
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(t, ast.Name) and t.id == "RENDER_PASSES"
            for t in node.targets
        )
    ]
    assert not redefined, (
        f"RENDER_PASSES must not be redefined in renderer.py "
        f"(lines {redefined})"
    )
