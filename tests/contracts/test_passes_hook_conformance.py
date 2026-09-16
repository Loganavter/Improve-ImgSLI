"""Base-images pass hook-seam conformance (Phase E1, hook-seam).

Pins the exact tab/engine interface from ruling 2 that E2 builds the
merged pass on verbatim:

* ``src/engine/passes/hooks.py`` declares the seam -- ``BaseImagesPassHooks``
  (``resolve_specs(ctx) -> list[ResidencySpec]`` + ``upload_tile(...)`` via
  the engine realizer base) and ``BaseImagesPassHookBase`` (realizer base +
  abstract ``resolve_specs``). Interface only: no pass implementation, no
  GPU/QRhi logic, no tab imports; the engine owns loop/budget/evict/order
  via ``TileResidencyRealizerBase.realize_specs``.
* Both tabs conform as-is (no tab edits in this wave): the fixed-pair
  rhi_renderer realizer and the multi-slot scene-passes realizer both
  subclass the engine realizer base and both implement the seam's upload
  parameter shape; the fixed-pair A0 manifest and the multi-slot D5 swap
  seam are the routing/decision surfaces E2 adapts.

Genuine gaps (adaptation happens in E2, never here) are asserted as
explicit shape facts, not failures: neither tab names a method
``resolve_specs`` yet (spec-building still lives inside the fixed-pair
``realize_tile_plan`` entry and the multi-slot per-call ``realize``
entry), and the multi-slot pass-level ``upload_tile(renderer, tile_key,
image, updates)`` is the swap machine's plain-path funnel -- a different
shape from the seam's residency ``upload_tile``, which E2 must not
conflate with it.
"""

from __future__ import annotations

import ast
import inspect

import pytest

from ._framework import ROOT, read

SEAM = ROOT / "src" / "engine" / "passes" / "hooks.py"
SEAM_PKG = ROOT / "src" / "engine" / "passes"
ENGINE_REALIZER = ROOT / "src" / "engine" / "cache" / "residency.py"

IC_RESIDENCY = (
    ROOT / "src" / "tabs" / "image_compare" / "canvas" / "rhi_renderer" / "residency.py"
)
IC_MANIFEST = ROOT / "src" / "engine" / "gpu" / "base_images_pass.py"
MC_RESIDENCY = (
    ROOT / "src" / "tabs" / "multi_compare" / "scene" / "passes" / "residency.py"
)
MC_BASE_IMAGES = (
    ROOT / "src" / "tabs" / "multi_compare" / "scene" / "passes" / "base_images.py"
)

# Exact seam signatures: method -> positional arg names (E2-verbatim).
_SEAM_SIGNATURES = {
    "resolve_specs": ["self", "ctx"],
    "upload_tile": [
        "self",
        "tile_service",
        "key",
        "index",
        "tile_image",
        "updates",
        "dirty_layers",
        "region",
    ],
}

# GPU-texture work the interface-only seam package must never name.
_GPU_MARKS = ("QRhi", "newTexture", "uploadTexture", "generateMips", "QRhiWidget")


def _parse(path):
    return ast.parse(read(path))


def _method_node(tree: ast.Module, class_name: str, method: str):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for stmt in node.body:
                if isinstance(stmt, ast.FunctionDef) and stmt.name == method:
                    return stmt
    return None


def _arg_names(func: ast.FunctionDef) -> list[str]:
    return [a.arg for a in func.args.args]


def _returns_none(func: ast.FunctionDef) -> bool:
    ret = func.returns
    return isinstance(ret, ast.Constant) and ret.value is None


def _unparse(node) -> str:
    try:
        return ast.unparse(node).strip()
    except Exception:
        return ""


def _class_bases(tree: ast.Module, class_name: str) -> list[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return [_unparse(b) for b in node.bases]
    return []


def _class_attr_value(tree: ast.Module, class_name: str, attr: str):
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


def _manifest_routes(path, class_name: str) -> bool:
    tree = _parse(path)
    for node in tree.body:
        value = None
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "RENDER_PASSES" for t in node.targets
        ):
            value = node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "RENDER_PASSES"
        ):
            value = node.value
        if isinstance(value, ast.List):
            return any(
                isinstance(elt, ast.Call)
                and isinstance(elt.func, ast.Name)
                and elt.func.id == class_name
                for elt in value.elts
            )
    return False


def _defines_function(path, name: str) -> bool:
    tree = _parse(path)
    return any(
        isinstance(node, ast.FunctionDef) and node.name == name
        for node in ast.walk(tree)
    )


def test_seam_package_holds_interface_only():
    py_files = sorted(
        p.name
        for p in SEAM_PKG.glob("*.py")
        if "__pycache__" not in p.parts
    )
    assert py_files == ["__init__.py", "hooks.py"], (
        f"src/engine/passes/ is the hook-seam interface only "
        f"(no pass implementations): {py_files}"
    )
    src = read(SEAM)
    hits = [mark for mark in _GPU_MARKS if mark in src]
    assert not hits, (
        f"hooks.py names GPU machinery {hits} -- the seam is interface "
        f"only (E2 writes the merged pass)"
    )
    tree = _parse(SEAM)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            top = node.module.split(".")[0]
            assert top in ("__future__", "abc", "typing", "engine"), (
                f"hooks.py imports '{node.module}' (line {node.lineno}): "
                f"the seam imports the engine realizer base plus stdlib "
                f"only -- never tab modules"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] in (
                    "abc",
                    "typing",
                ), (f"hooks.py imports '{alias.name}': stdlib only")
    assert "tabs." not in src and "plugins." not in src, (
        "hooks.py references a tab/plugin module -- the engine never "
        "names its callers"
    )


def test_seam_hook_signatures_exact():
    tree = _parse(SEAM)
    assert "BaseImagesPassHooks" in {
        n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)
    }, "hooks.py must declare the BaseImagesPassHooks protocol"
    assert "Protocol" in _class_bases(tree, "BaseImagesPassHooks"), (
        "BaseImagesPassHooks must be a typing.Protocol (structural seam)"
    )
    for method, expected in _SEAM_SIGNATURES.items():
        func = _method_node(tree, "BaseImagesPassHooks", method)
        assert func is not None, (
            f"BaseImagesPassHooks must declare {method}{tuple(expected)} "
            f"(E2 builds on this verbatim)"
        )
        assert _arg_names(func) == expected, (
            f"BaseImagesPassHooks.{method} signature drift: expected "
            f"{expected}, got {_arg_names(func)}"
        )
    resolve = _method_node(tree, "BaseImagesPassHooks", "resolve_specs")
    assert _unparse(resolve.returns) == "list[ResidencySpec]", (
        f"resolve_specs must return list[ResidencySpec], got "
        f"{_unparse(resolve.returns)!r}"
    )
    upload = _method_node(tree, "BaseImagesPassHooks", "upload_tile")
    assert _returns_none(upload), "seam upload_tile must return None"
    assert "TileResidencyRealizerBase" in _class_bases(
        tree, "BaseImagesPassHookBase"
    ), "BaseImagesPassHookBase must extend the engine realizer base"
    base_resolve = _method_node(tree, "BaseImagesPassHookBase", "resolve_specs")
    assert base_resolve is not None, (
        "BaseImagesPassHookBase must declare abstract resolve_specs"
    )
    assert _arg_names(base_resolve) == _SEAM_SIGNATURES["resolve_specs"]
    assert _unparse(base_resolve.returns) == "list[ResidencySpec]"
    decorators = [
        _unparse(d) for d in getattr(base_resolve, "decorator_list", [])
    ]
    assert "abstractmethod" in decorators, (
        "BaseImagesPassHookBase.resolve_specs must stay abstract "
        "(interface only, E2 fills it in)"
    )


def test_engine_owns_realize_loop():
    assert _defines_function(ENGINE_REALIZER, "realize_specs"), (
        "TileResidencyRealizerBase must own realize_specs (engine owns "
        "loop/budget/evict/order)"
    )
    for path in (IC_RESIDENCY, MC_RESIDENCY):
        assert not _defines_function(path, "realize_specs"), (
            f"{path.name} defines realize_specs: the realize loop is "
            f"engine-owned, tabs only resolve specs + upload tiles"
        )


def test_ic_conforms_as_is():
    tree = _parse(IC_RESIDENCY)
    assert "TileResidencyRealizerBase" in _class_bases(
        tree, "TileResidencyRealizer"
    ), "fixed-pair TileResidencyRealizer must subclass the engine base"
    func = _method_node(tree, "TileResidencyRealizer", "_upload_tile")
    assert func is not None, (
        "fixed-pair TileResidencyRealizer must provide _upload_tile via "
        "the engine realizer base"
    )
    assert _arg_names(func) == _SEAM_SIGNATURES["upload_tile"], (
        f"fixed-pair _upload_tile shape must match the seam upload_tile "
        f"(rename-only gap for E2): expected "
        f"{_SEAM_SIGNATURES['upload_tile']}, got {_arg_names(func)}"
    )
    assert _returns_none(func)
    public = _method_node(tree, "TileResidencyRealizer", "upload_tile")
    assert public is not None, (
        "fixed-pair TileResidencyRealizer must provide the public seam "
        "upload_tile (Phase F rename-only promotion of _upload_tile)"
    )
    assert _arg_names(public) == _SEAM_SIGNATURES["upload_tile"], (
        f"fixed-pair upload_tile shape must match the seam upload_tile: "
        f"expected {_SEAM_SIGNATURES['upload_tile']}, got "
        f"{_arg_names(public)}"
    )
    assert _returns_none(public)
    manifest_tree = _parse(IC_MANIFEST)
    role = _class_attr_value(manifest_tree, "BaseImagesPass", "stack_role")
    assert role == ("CanvasStackRole", "IMAGE_OVERLAY_CONTENT"), (
        "merged engine pass must declare the shared base role directly "
        "(Phase F: tab A0 manifest retired here; full dogma: "
        "test_ic_render_manifest)"
    )
    assert _method_node(tree, "TileResidencyRealizer", "resolve_specs") is None, (
        "fixed-pair spec-building still lives in realize_tile_plan -- E2 "
        "lifts it behind resolve_specs (adaptation, not a gap to fix here)"
    )


def test_mc_conforms_as_is():
    tree = _parse(MC_RESIDENCY)
    assert "TileResidencyRealizerBase" in _class_bases(
        tree, "_SlotUploadRealizer"
    ), "multi-slot _SlotUploadRealizer must subclass the engine base"
    func = _method_node(tree, "_SlotUploadRealizer", "_upload_tile")
    assert func is not None, (
        "multi-slot _SlotUploadRealizer must provide _upload_tile via "
        "the engine realizer base"
    )
    assert _arg_names(func) == _SEAM_SIGNATURES["upload_tile"], (
        f"multi-slot _upload_tile shape must match the seam upload_tile "
        f"(rename-only gap for E2): expected "
        f"{_SEAM_SIGNATURES['upload_tile']}, got {_arg_names(func)}"
    )
    assert _returns_none(func)
    base_tree = _parse(MC_BASE_IMAGES)
    swap = _method_node(base_tree, "BaseImagesPass", "resolve_swap_spec")
    assert swap is not None, (
        "multi-slot BaseImagesPass must keep the D5 resolve_swap_spec seam"
    )
    assert _arg_names(swap) == ["self", "tile_service", "sid", "source"], (
        f"resolve_swap_spec signature drift: got {_arg_names(swap)}"
    )
    plain = _method_node(base_tree, "BaseImagesPass", "upload_tile")
    assert plain is not None, (
        "multi-slot BaseImagesPass must keep the D5 plain-path "
        "upload_tile funnel"
    )
    assert _arg_names(plain) == ["self", "renderer", "tile_key", "image", "updates"], (
        f"swap-machine upload_tile is the plain-path funnel, not the seam "
        f"residency upload -- E2 must not conflate them; got "
        f"{_arg_names(plain)}"
    )
    assert _method_node(tree, "_SlotUploadRealizer", "resolve_specs") is None, (
        "multi-slot spec-building still lives in the per-call realize "
        "entry -- E2 lifts it behind resolve_specs (adaptation, not a gap "
        "to fix here)"
    )
    assert _manifest_routes(MC_BASE_IMAGES, "BaseImagesPass"), (
        "multi-slot RENDER_PASSES must keep routing BaseImagesPass "
        "(full dogma: test_mc_pass_contract_shape)"
    )


def test_seam_importable_from_both_tabs_perspective():
    from engine.cache.residency import TileResidencyRealizerBase
    from engine.passes.hooks import BaseImagesPassHookBase, BaseImagesPassHooks

    assert issubclass(BaseImagesPassHookBase, TileResidencyRealizerBase)
    assert inspect.isabstract(BaseImagesPassHookBase), (
        "hook base stays abstract -- E2's merged pass provides the hooks"
    )
    with pytest.raises(TypeError):
        BaseImagesPassHookBase(tile_cache_budget_bytes=1)
    assert hasattr(BaseImagesPassHooks, "resolve_specs")
    assert hasattr(BaseImagesPassHooks, "upload_tile")
    sig = inspect.signature(BaseImagesPassHooks.resolve_specs)
    assert list(sig.parameters) == _SEAM_SIGNATURES["resolve_specs"]
    up = inspect.signature(BaseImagesPassHooks.upload_tile)
    assert list(up.parameters) == _SEAM_SIGNATURES["upload_tile"]
