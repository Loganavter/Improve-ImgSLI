"""Multi-compare base-image pass contract shape (Phase D1, mc-signatures).

Pins the image_compare-mirroring render-pass contract on
``BaseImagesPass`` (``src/tabs/multi_compare/scene/passes/base_images.py``):

* ``initialize(rhi, target)`` / ``prepare(widget, ctx, updates)`` /
  ``record(command_buffer, widget, ctx)`` -- exact arg names, matching
  ``magnifier_pass.py`` (``initialize`` ~448, ``prepare`` ~585,
  ``record`` ~1017). The old split-phase shapes
  (``initialize(renderer, target)``, ``realize_residency`` /
  ``finish_prepare``, ``record(renderer, ctx, command_buffer)``) are gone.
* ``RENDER_PASSES`` routes ``BaseImagesPass``; the renderer takes its
  ``image_pass`` from that manifest instead of instantiating directly.
* ``stack_role`` (a ``CanvasStackRole`` member) and ``visibility``
  (explicit ``SceneVisibility.ALL``) -- never hardcoded
  ``layer=<int>`` / ``priority=<int>``. ``ALL`` is load-bearing, not a
  placeholder: ``MultiCompareRenderContext`` carries no render-mode
  signal, so ``iter_active_render_passes``' resolver defaults to
  ``PREVIEW`` (see ``canvas/features/drag_drop_overlay/passes.py``) --
  narrowing this to ``INTERACTIVE`` would silently disable the base pass.

Dogma source: docs/dev/CONTRACTS.md (CanvasRenderPass / stacking policy),
docs/dev/rendering/render-pass-contract.md. D2 (tile_geometry) and D3
(residency) consume these shapes unchanged.
"""

from __future__ import annotations

import ast
import re

from ._framework import ROOT, read

MC_SCENE = ROOT / "src" / "tabs" / "multi_compare" / "scene"
MC_BASE_IMAGES = MC_SCENE / "passes" / "base_images.py"
MC_RENDERER = MC_SCENE / "renderer.py"

# Pinned contract shapes: method -> exact positional arg names.
_CONTRACT_SHAPES = {
    "initialize": ["self", "rhi", "target"],
    "prepare": ["self", "widget", "ctx", "updates"],
    "record": ["self", "command_buffer", "widget", "ctx"],
}

# Old split-phase shapes that must not come back.
_REMOVED_METHODS = ("realize_residency", "finish_prepare")

_HARDCODED_LAYER_RE = re.compile(r"^\s*(layer|priority)\s*=\s*\d+", re.MULTILINE)


def _parse(path):
    return ast.parse(read(path))


def _method_arg_names(tree: ast.Module, class_name: str, method: str):
    """Positional arg names for ``class_name.method``, or ``None``."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for stmt in node.body:
                if (
                    isinstance(stmt, ast.FunctionDef)
                    and stmt.name == method
                ):
                    return [arg.arg for arg in stmt.args.args]
    return None


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
    tree = _parse(MC_BASE_IMAGES)
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
                f"{MC_BASE_IMAGES.name}: RENDER_PASSES entries must be "
                f"plain class instantiations, got {ast.dump(elt)}"
            )
            entries.append(elt.func.id)
        return tree, entries
    raise AssertionError(f"{MC_BASE_IMAGES.name} must define RENDER_PASSES = [...]")


def _image_pass_calls(tree: ast.Module, method: str):
    """All ``self.image_pass.<method>(...)`` call nodes in renderer.py."""
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == method
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "image_pass"
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id == "self"
        ):
            found.append(node)
    return found


def test_contract_signatures():
    tree = _parse(MC_BASE_IMAGES)
    for method, expected in _CONTRACT_SHAPES.items():
        actual = _method_arg_names(tree, "BaseImagesPass", method)
        assert actual is not None, (
            f"BaseImagesPass must define {method}{tuple(expected)} "
            f"(contract shape, mirrors magnifier_pass)"
        )
        assert actual == expected, (
            f"BaseImagesPass.{method} signature drift: "
            f"expected {expected}, got {actual} "
            f"(D2/D3 consume these shapes unchanged)"
        )


def test_split_phase_methods_removed():
    tree = _parse(MC_BASE_IMAGES)
    defined = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }
    for name in _REMOVED_METHODS:
        assert name not in defined, (
            f"BaseImagesPass.{name} must stay removed: the renderer calls "
            f"contract-shape prepare() (split-phase asymmetry is closed)"
        )
    src = read(MC_BASE_IMAGES)
    assert "def realize_residency" not in src
    assert "def finish_prepare" not in src


def test_render_passes_manifest_routes_base_images():
    tree, entries = _manifest_entry_classes()
    assert "BaseImagesPass" in entries, (
        "RENDER_PASSES must route BaseImagesPass "
        "(renderer takes image_pass from the manifest)"
    )
    defined = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }
    assert "BaseImagesPass" in defined


def test_stack_role_and_visibility_declared():
    tree, _ = _manifest_entry_classes()
    role = _class_attr_value(tree, "BaseImagesPass", "stack_role")
    assert role is not None and role[0] == "CanvasStackRole", (
        "BaseImagesPass must declare stack_role = CanvasStackRole.<ROLE> "
        "(do not hardcode layer/priority)"
    )
    visibility = _class_attr_value(tree, "BaseImagesPass", "visibility")
    assert visibility == ("SceneVisibility", "ALL"), (
        f"BaseImagesPass.visibility must stay explicit SceneVisibility.ALL "
        f"(got {visibility}): the modeless MC ctx resolves to PREVIEW by "
        f"default, so anything narrower silently disables the base pass"
    )


def test_no_hardcoded_layer_or_priority():
    for path in (MC_BASE_IMAGES, MC_RENDERER):
        src = read(path)
        hits = [
            f"{path.name}:{src[: m.start()].count(chr(10)) + 1}"
            for m in _HARDCODED_LAYER_RE.finditer(src)
        ]
        assert not hits, (
            "hardcoded layer/priority -- use stack_role:\n  - "
            + "\n  - ".join(hits)
        )


def test_renderer_routes_image_pass_via_manifest():
    tree = _parse(MC_RENDERER)
    direct = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "BaseImagesPass"
    ]
    assert not direct, (
        f"renderer.py must not instantiate BaseImagesPass directly "
        f"(route via RENDER_PASSES, lines {direct})"
    )
    imports_manifest = any(
        isinstance(node, ast.ImportFrom)
        and (node.module or "").endswith("scene.passes")
        and any(alias.name == "RENDER_PASSES" for alias in node.names)
        for node in ast.walk(tree)
    )
    assert imports_manifest, (
        "renderer.py must import RENDER_PASSES from scene.passes"
    )
    assert "RENDER_PASSES" in read(MC_RENDERER)


def test_renderer_uses_contract_call_shapes():
    tree = _parse(MC_RENDERER)

    init_calls = _image_pass_calls(tree, "initialize")
    assert init_calls, "renderer must initialize image_pass"
    for call in init_calls:
        assert len(call.args) == 2, (
            f"image_pass.initialize must take (rhi, target), "
            f"line {call.lineno}"
        )
        first = call.args[0]
        assert isinstance(first, ast.Attribute) and first.attr == "rhi", (
            f"image_pass.initialize first arg must be self.rhi "
            f"(not the renderer), line {call.lineno}"
        )

    prepare_calls = _image_pass_calls(tree, "prepare")
    assert prepare_calls, "renderer must prepare image_pass"
    for call in prepare_calls:
        assert len(call.args) == 3, (
            f"image_pass.prepare must take (widget, ctx, updates), "
            f"line {call.lineno}"
        )

    record_calls = _image_pass_calls(tree, "record")
    assert record_calls, "renderer must record image_pass"
    for call in record_calls:
        kinds = [
            (
                type(a).__name__,
                getattr(a, "id", None) or getattr(a, "attr", None),
            )
            for a in call.args
        ]
        assert len(call.args) == 3, (
            f"image_pass.record must take (command_buffer, widget, ctx), "
            f"line {call.lineno}: {kinds}"
        )
        assert isinstance(call.args[0], ast.Name) and call.args[0].id == (
            "command_buffer"
        ), (
            f"image_pass.record first arg must be command_buffer "
            f"(contract order), line {call.lineno}: {kinds}"
        )
        assert isinstance(call.args[1], ast.Attribute), (
            f"image_pass.record second arg must be the widget "
            f"(contract order), line {call.lineno}: {kinds}"
        )

    for old in _REMOVED_METHODS:
        assert not _image_pass_calls(tree, old), (
            f"renderer must not call image_pass.{old} "
            f"(folded into prepare)"
        )
