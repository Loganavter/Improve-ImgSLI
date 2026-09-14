"""Image-compare base-image render-pass manifest dogma (Phase A0).

Mirrors multi_compare's ``scene/passes/base_images.py`` 2B shape for the
image_compare renderer:

* ``tabs/image_compare/canvas/rhi_renderer/passes.py`` declares a
  module-level ``RENDER_PASSES`` list (base-image stage, matching the live
  ``RhiCanvasRenderer.render`` wiring: base array draw first, then the
  registry-discovered feature passes).
* each entry's class declares ``stack_role`` (a ``CanvasStackRole`` member)
  and ``visibility`` (a ``SceneVisibility`` member) -- never hardcoded
  ``layer=<int>`` / ``priority=<int>``.
* role parity with multi_compare's ``BaseImagesPass`` so the central
  stacking policy orders both tabs' base stages identically.
* ``renderer.py`` wiring is untouched: feature passes still come from
  ``registry().get_render_passes()``, the draw submit still goes through
  ``submit_array_draw``, and no ``RENDER_PASSES`` is (re)defined there --
  the manifest lives only in ``passes.py``.

Dogma source: docs/dev/CONTRACTS.md (CanvasRenderPass / stacking policy).
"""

from __future__ import annotations

import ast
import re

from ._framework import ROOT, read

IC_RHI_RENDERER = (
    ROOT / "src" / "tabs" / "image_compare" / "canvas" / "rhi_renderer"
)
IC_MANIFEST = IC_RHI_RENDERER / "passes.py"
IC_RENDERER = IC_RHI_RENDERER / "renderer.py"
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
    return ast.parse(read(path))


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


def _manifest_entry_classes():
    """``[(class_name, ...)]`` for each ``RENDER_PASSES`` list element."""
    tree = _parse(IC_MANIFEST)
    for node in tree.body:
        value = None
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "RENDER_PASSES"
            for t in node.targets
        ):
            value = node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "RENDER_PASSES"
        ):
            value = node.value
        if value is None or not isinstance(value, ast.List):
            continue
        entries = []
        for elt in value.elts:
            assert isinstance(elt, ast.Call) and isinstance(
                elt.func, ast.Name
            ), (
                f"{IC_MANIFEST.name}: RENDER_PASSES entries must be "
                f"plain class instantiations, got {ast.dump(elt)}"
            )
            entries.append(elt.func.id)
        return tree, entries
    raise AssertionError(f"{IC_MANIFEST.name} must define RENDER_PASSES = [...]")


def test_manifest_module_defines_render_passes():
    assert IC_MANIFEST.is_file(), (
        "missing image_compare base-image pass manifest: "
        "src/tabs/image_compare/canvas/rhi_renderer/passes.py"
    )
    tree, entries = _manifest_entry_classes()
    assert entries, "RENDER_PASSES must not be empty"
    defined = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }
    for name in entries:
        assert name in defined, (
            f"RENDER_PASSES entry {name!r} must be a class defined in "
            f"{IC_MANIFEST.name}"
        )


def test_manifest_entries_declare_stack_role_and_visibility():
    tree, entries = _manifest_entry_classes()
    for name in entries:
        role = _class_attr_value(tree, name, "stack_role")
        assert role is not None and role[0] == "CanvasStackRole", (
            f"{name} must declare stack_role = CanvasStackRole.<ROLE> "
            f"(do not hardcode layer/priority)"
        )
        visibility = _class_attr_value(tree, name, "visibility")
        assert visibility is not None and visibility[0] == "SceneVisibility", (
            f"{name} must declare visibility = SceneVisibility.<SCOPE>"
        )


def test_manifest_role_parity_with_multi_compare():
    """IC base stage resolves through the same stacking-policy role as MC."""
    mc_tree = _parse(MC_BASE_IMAGES)
    mc_role = _class_attr_value(mc_tree, "BaseImagesPass", "stack_role")
    mc_vis = _class_attr_value(mc_tree, "BaseImagesPass", "visibility")
    assert mc_role is not None and mc_vis is not None, (
        "multi_compare BaseImagesPass must keep its stack_role/visibility "
        "attrs (parity reference)"
    )
    tree, entries = _manifest_entry_classes()
    assert len(entries) == 1, (
        "IC manifest is the single base-image stage (feature passes keep "
        "their own passes.py manifests); expected exactly 1 entry, "
        f"got {len(entries)}"
    )
    assert _class_attr_value(tree, entries[0], "stack_role") == mc_role, (
        f"IC {entries[0]}.stack_role must match multi_compare "
        f"BaseImagesPass.stack_role ({mc_role})"
    )
    assert _class_attr_value(tree, entries[0], "visibility") == mc_vis, (
        f"IC {entries[0]}.visibility must match multi_compare "
        f"BaseImagesPass.visibility ({mc_vis})"
    )


def test_manifest_no_hardcoded_layer_or_priority():
    for path in (IC_MANIFEST, IC_RENDERER):
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
        f"RENDER_PASSES must live only in passes.py, not renderer.py "
        f"(lines {redefined})"
    )
