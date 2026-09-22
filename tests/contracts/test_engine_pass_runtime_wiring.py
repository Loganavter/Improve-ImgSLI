"""Engine base-images pass runtime wiring on the multi_compare hot path (R2).

Pins that the multi_compare renderer hot path
(``renderer.render`` -> ``BaseImagesPass.prepare`` ->
``_realize_tile_residency`` -> ``residency.realize`` ->
``_SlotUploadRealizer.realize``) instantiates the merged engine
``BaseImagesPass`` (``src/engine/gpu/base_images_pass.py``) with a
tab-bound ``BaseImagesSpecHooks`` bundle and feeds the frame through the
engine ``realize`` -- there is no second residency loop on the tab side.

Owned by R2 only (interface R-b): asserts the MC side exclusively, never
the fixed-pair tab (R3's concurrent wave owns that tree).

* ``test_mc_hot_path_instantiates_engine_pass`` -- MC residency imports
  the engine pass and constructs it inside ``_SlotUploadRealizer.realize``.
* ``test_mc_hot_path_feeds_engine_realize`` -- that same ``realize``
  calls the engine pass's ``realize`` (with the tab's ``ctx``,
  ``dirty_layers`` and ``extra_protect_keys``) and never calls the
  inherited ``realize_specs`` loop directly anymore.
* ``test_mc_hooks_bundle_bound_by_reference`` -- the hooks bundle carries
  exactly the E1 seam collaborators (``resolve_specs`` + ``upload_tile``)
  bound to tab callables, and the tab keeps the public ``upload_tile``
  seam (rename-only promotion of ``_upload_tile``, mirroring the
  fixed-pair realizer).
* ``test_mc_spec_build_split`` -- spec-building lives in the module-level
  ``build_slot_specs`` builder (single ``lod_key_and_source`` resolution
  per frame) behind the frame's memoized ``resolve_specs``, shared by the
  explicit spec-build step and the engine feed.
* ``test_no_second_residency_loop_in_mc_scene`` -- ``realize_specs`` is
  defined nowhere under the multi_compare scene tree (single home:
  ``engine/cache/residency.py``).
"""

from __future__ import annotations

import ast

from ._framework import ROOT, read, rel

MC_RESIDENCY = (
    ROOT / "src" / "tabs" / "multi_compare" / "scene" / "passes" / "residency.py"
)
MC_SCENE = ROOT / "src" / "tabs" / "multi_compare" / "scene"
ENGINE_PASS = ROOT / "src" / "engine" / "gpu" / "base_images_pass.py"

_ENGINE_PASS_MODULE = "engine.gpu.base_images_pass"


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


def _unparse(node) -> str:
    try:
        return ast.unparse(node).strip()
    except Exception:
        return ""


def _engine_pass_alias(tree: ast.Module) -> str | None:
    """Local name the engine ``BaseImagesPass`` is imported under (aliased
    on the tab side so it never collides with the tab-hooks surface)."""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == _ENGINE_PASS_MODULE
        ):
            for alias in node.names:
                if alias.name == "BaseImagesPass":
                    return alias.asname or alias.name
    return None


def test_mc_hot_path_instantiates_engine_pass():
    assert MC_RESIDENCY.is_file(), f"missing MC residency: {rel(MC_RESIDENCY)}"
    tree = _parse(MC_RESIDENCY)
    alias = _engine_pass_alias(tree)
    assert alias is not None, (
        f"{rel(MC_RESIDENCY)} must import BaseImagesPass from "
        f"{_ENGINE_PASS_MODULE} (the merged engine pass on the MC hot path)"
    )
    realize = _method_node(tree, "_SlotUploadRealizer", "realize")
    assert realize is not None, (
        "_SlotUploadRealizer.realize is the MC hot-path entry (frozen shape)"
    )
    instantiated = any(
        isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == alias)
            or (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "BaseImagesPass"
            )
        )
        for node in ast.walk(realize)
    )
    assert instantiated, (
        f"_SlotUploadRealizer.realize must instantiate the engine "
        f"BaseImagesPass (imported as {alias!r}): the runtime flows through "
        f"engine realize"
    )


def test_mc_hot_path_feeds_engine_realize():
    tree = _parse(MC_RESIDENCY)
    realize = _method_node(tree, "_SlotUploadRealizer", "realize")
    assert realize is not None
    feed_calls = [
        node
        for node in ast.walk(realize)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "realize"
    ]
    assert feed_calls, (
        "_SlotUploadRealizer.realize must call the engine pass's realize "
        "(resolve -> realize_specs -> return lives in the engine)"
    )
    keywords = set()
    for call in feed_calls:
        keywords.update(kw.arg for kw in call.keywords)
    assert "dirty_layers" in keywords and "extra_protect_keys" in keywords, (
        f"engine realize feed must carry dirty_layers + extra_protect_keys "
        f"(tab-owned mip dirt + fallback-LOD protection), got {sorted(keywords)}"
    )
    direct_loop = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "realize_specs"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
        for node in ast.walk(realize)
    )
    assert not direct_loop, (
        "_SlotUploadRealizer.realize must not call self.realize_specs "
        "directly: exactly one feed, through the engine pass (no second "
        "residency loop)"
    )


def test_mc_hooks_bundle_bound_by_reference():
    tree = _parse(MC_RESIDENCY)
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == _ENGINE_PASS_MODULE
        and any(a.name == "BaseImagesSpecHooks" for a in node.names)
        for node in ast.walk(tree)
    ), (
        f"{rel(MC_RESIDENCY)} must import BaseImagesSpecHooks from "
        f"{_ENGINE_PASS_MODULE} (C3 hook-bundle pattern)"
    )
    bundles = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "BaseImagesSpecHooks")
            or (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "BaseImagesSpecHooks"
            )
        )
    ]
    assert bundles, (
        "MC hot path must build a BaseImagesSpecHooks bundle for the engine pass"
    )
    for bundle in bundles:
        keys = {kw.arg for kw in bundle.keywords}
        assert keys == {"resolve_specs", "upload_tile"}, (
            f"BaseImagesSpecHooks bundle must carry exactly the E1 seam "
            f"collaborators, got {sorted(keys)} (bound by reference, no "
            f"adaptation logic)"
        )
    public = _method_node(tree, "_SlotUploadRealizer", "upload_tile")
    assert public is not None, (
        "multi-slot _SlotUploadRealizer must provide the public seam "
        "upload_tile (rename-only promotion of _upload_tile, mirroring the "
        "fixed-pair realizer)"
    )
    assert _arg_names(public) == [
        "self",
        "tile_service",
        "key",
        "index",
        "tile_image",
        "updates",
        "dirty_layers",
        "region",
    ], (
        f"multi-slot upload_tile shape must match the seam upload_tile, got "
        f"{_arg_names(public)}"
    )


def test_mc_spec_build_split():
    tree = _parse(MC_RESIDENCY)
    builder = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "build_slot_specs"
        ),
        None,
    )
    assert builder is not None, (
        "MC residency must resolve this call's specs in the module-level "
        "build_slot_specs builder (spec-build half of the realize split)"
    )
    frame_resolve = _method_node(tree, "_SlotSpecFrame", "resolve_specs")
    assert frame_resolve is not None, (
        "_SlotSpecFrame must front the builder behind the E1 resolve_specs "
        "seam name (memoized: exactly one lod_key_and_source resolution per "
        "frame, shared by the spec-build step and the engine feed)"
    )
    assert _arg_names(frame_resolve) == ["self", "ctx"], (
        f"_SlotSpecFrame.resolve_specs signature drift: expected "
        f"['self', 'ctx'], got {_arg_names(frame_resolve)}"
    )
    assert _unparse(frame_resolve.returns) == "list[ResidencySpec]", (
        f"_SlotSpecFrame.resolve_specs must return list[ResidencySpec], got "
        f"{_unparse(frame_resolve.returns)!r}"
    )
    assert any(
        isinstance(node, ast.Call)
        and _unparse(node.func) == "build_slot_specs"
        for node in ast.walk(frame_resolve)
    ), (
        "_SlotSpecFrame.resolve_specs must delegate to build_slot_specs "
        "(single spec-build home)"
    )
    # The E1 hook-conformance dogma pins that spec-building is NOT a
    # ``_SlotUploadRealizer.resolve_specs`` method (that class keeps the
    # realizer-base shape); the frame carries the seam method instead.
    assert _method_node(tree, "_SlotUploadRealizer", "resolve_specs") is None, (
        "_SlotUploadRealizer must not grow a resolve_specs method "
        "(hook-conformance contract: spec-building lives in the frame, the "
        "realizer keeps _upload_tile + the engine feed)"
    )


def test_no_second_residency_loop_in_mc_scene():
    owners = []
    for path in sorted(MC_SCENE.rglob("*.py")):
        if "__pycache__" in path.parts or "tests" in path.parts:
            continue
        try:
            tree = ast.parse(read(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for stmt in node.body:
                    if (
                        isinstance(stmt, ast.FunctionDef)
                        and stmt.name == "realize_specs"
                    ):
                        owners.append(f"{rel(path)}:{node.name}")
    assert owners == [], (
        f"realize_specs must have no home under the MC scene tree (single "
        f"home: engine/cache/residency.py): {owners}"
    )
