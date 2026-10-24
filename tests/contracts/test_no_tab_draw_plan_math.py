"""R4: draw-plan math has a single engine home (flag-day, lift-then-delete).

Pins that coverage/geometry math for tiled draw plans lives ONLY in
``src/engine/cache/draw_plans.py`` (rect tuples, ``UniformTileGrid``,
letterboxes, ``TileTextureService`` -- the ``tile_coverage`` precedent),
while the tab item classes adapt at the call surface:

* ``src/tabs/image_compare/canvas/rhi_renderer/draw_plan.py`` --
  ``build_array_draw_plan`` is a thin caller of the engine pair builder
  (enumerate via the shared residency-spec helper, residency-filter via
  ``slot_for``, convert engine plan structs to ``ArrayDrawItem``). No
  common-space/overlap/bbox/diff math of its own.
* ``src/tabs/multi_compare/scene/tile_geometry.py`` --
  ``build_slot_draw_plan`` / ``build_slot_array_tiles`` are thin callers
  of the engine slot builder; ``drop_covered_fallback_tiles`` is a thin
  tile<->rect adapter over the engine rect-level drop of the same name;
  ``_visible_slot_image_rect`` stays (the residency-spec pass imports the
  name) as a one-line delegate of the engine visible-rect derivation.
* ``BaseImagesPass._prepare_array_plan`` builds from those engine-backed
  names and reuses the engine content-scale helper.

Complements (never contradicts) ``test_coverage_uses_slot_for.py``: the
``slot_for`` residency guards it pins stay tab-side at the call surface;
everything geometric moved engine-side. Boundary names pinned here are
the vocabulary later waves (R5/R6) must reuse instead of inventing
seconds.
"""

from __future__ import annotations

import ast

import pytest
import re

from ._framework import ROOT, iter_py, parse, read, rel

pytestmark = pytest.mark.slow

ENGINE_DRAW_PLANS = ROOT / "src" / "engine" / "cache" / "draw_plans.py"
IC_DRAW_PLAN = (
    ROOT / "src" / "tabs" / "image_compare" / "canvas" / "rhi_renderer" / "draw_plan.py"
)
MC_TILE_GEOMETRY = (
    ROOT / "src" / "tabs" / "multi_compare" / "scene" / "tile_geometry.py"
)
MC_BASE_IMAGES = (
    ROOT / "src" / "tabs" / "multi_compare" / "scene" / "passes" / "base_images.py"
)

_PLAN_TILE_FIELDS = ["rect", "index"]

_PAIR_PLAN_FIELDS = [
    "rect1",
    "rect2",
    "index1",
    "index2",
    "bbox",
    "rect_diff",
    "layer1",
    "layer2",
    "layer_diff",
    "array_index",
    "content_scale",
    "content_scale_diff",
]

# Engine boundary signatures: function -> positional arg names.
_ENGINE_SIGNATURES = {
    "slot_visible_rect": ["pan_offset", "fit_scale", "zoom", "grid"],
    "plan_tiles_for_grid": ["tile_service", "source_id", "visible_rect"],
    "build_slot_plan_tiles": [
        "tile_service",
        "slot_id",
        "pan_offset",
        "fit_scale",
        "zoom",
    ],
    "drop_covered_fallback_tiles": ["fallback_rects", "current_rects"],
    "best_overlap_tile_index": ["grid", "rect"],
    "content_scale_for": ["content_size", "layer_px"],
    "build_compare_pair_plan": [
        "tile_service",
        "key1",
        "key2",
        "letterbox1",
        "letterbox2",
    ],
}

_PAIR_PLAN_KWONLY = {
    "side1",
    "side2",
    "diff_key",
    "diff_tiles",
    "layer_px",
}

# Geometry/coverage call names that must not appear tab-side after the move
# (checked as AST call attributes/names, so ``content_scale`` fields and
# ``slot_for`` residency guards never trip them).
_TAB_FORBIDDEN_CALLS = frozenset(
    {
        "to_common_space",
        "rects_overlap",
        "intersection_rect",
        "covered_fraction",
        "_covered_fraction",
        "best_tile_overlap_index",
        "_apron_rect",
        "_visible_side_image_rect",
        "visible_tiles",
    }
)

# Geometry/coverage definitions that must not exist tab-side after the move
# (``_visible_slot_image_rect`` is the deliberate exception: the
# residency-spec pass imports the name, so it stays as a one-line engine
# delegate, pinned by ``test_mc_visible_rect_stays_a_delegate``).
_TAB_FORBIDDEN_DEFS = frozenset(
    {
        "to_common_space",
        "rects_overlap",
        "intersection_rect",
        "covered_fraction",
        "slot_visible_rect",
        "plan_tiles_for_grid",
        "build_slot_plan_tiles",
        "best_overlap_tile_index",
        "content_scale_for",
        "build_compare_pair_plan",
        "_array_side_tiles",
        "_resolve_diff_tile_index",
        "_best_diff_tile_index",
        "_content_scale",
    }
)

_FORBIDDEN_TEXT_RES = [
    re.compile(r"tabs\.[A-Za-z_]"),
    re.compile(r"plugins\.[A-Za-z_]"),
    re.compile(r"src/tabs"),
    re.compile(r"src/plugins"),
    re.compile(r"core/store"),
    re.compile(r"core\.store"),
]


def _parse(path):
    tree = parse(path)
    if tree is None:
        raise SyntaxError(f"cannot parse {path}")
    return tree


def _dataclass_fields(tree: ast.Module, class_name: str) -> list[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            fields = []
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    fields.append(stmt.target.id)
            return fields
    return []


def _function_node(tree: ast.Module, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _arg_names(func) -> list[str]:
    return [a.arg for a in func.args.args]


def _kwonly_names(func) -> set[str]:
    return {a.arg for a in func.args.kwonlyargs}


def _call_names_in(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute):
            names.add(func.attr)
    return names


def _defined_names(tree: ast.Module) -> set[str]:
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }


def _function_segment(path, func_name: str) -> str:
    text = read(path)
    tree = parse(path)
    assert tree is not None, f"{rel(path)}: unparsable"
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == func_name
        ):
            seg = ast.get_source_segment(text, node)
            assert seg is not None, f"{rel(path)}:{node.lineno} no source segment"
            return seg
    raise AssertionError(f"{rel(path)}: no function {func_name!r}")


def test_engine_module_pins_plan_struct_vocabulary():
    assert ENGINE_DRAW_PLANS.is_file(), (
        "missing engine draw-plan module: src/engine/cache/draw_plans.py"
    )
    tree = _parse(ENGINE_DRAW_PLANS)
    assert _dataclass_fields(tree, "PlanTile") == _PLAN_TILE_FIELDS, (
        f"PlanTile fields drift: got {_dataclass_fields(tree, 'PlanTile')}"
    )
    assert _dataclass_fields(tree, "ComparePairPlan") == _PAIR_PLAN_FIELDS, (
        f"ComparePairPlan fields drift: got "
        f"{_dataclass_fields(tree, 'ComparePairPlan')}"
    )
    for func_name, expected in _ENGINE_SIGNATURES.items():
        func = _function_node(tree, func_name)
        assert func is not None, (
            f"engine draw_plans must define {func_name}{tuple(expected)} "
            f"(R4 boundary vocabulary)"
        )
        assert _arg_names(func) == expected, (
            f"engine {func_name} signature drift: expected {expected}, "
            f"got {_arg_names(func)}"
        )
    pair_fn = _function_node(tree, "build_compare_pair_plan")
    assert _PAIR_PLAN_KWONLY <= _kwonly_names(pair_fn), (
        f"build_compare_pair_plan lost keyword inputs: have "
        f"{sorted(_kwonly_names(pair_fn))}, need at least "
        f"{sorted(_PAIR_PLAN_KWONLY)}"
    )
    from engine.cache import draw_plans as _plans

    assert _plans.SLIVER_MIN == 0.002, "SLIVER_MIN drift (parity constant)"
    assert _plans.BBOX_EPS == 0.003, "BBOX_EPS drift (parity constant)"
    assert _plans.FULL_TILE_RECT == (0.0, 0.0, 1.0, 1.0)


def test_engine_module_is_interface_clean():
    src = read(ENGINE_DRAW_PLANS)
    for tab_item in ("ArrayDrawItem", "SlotDrawItem", "SlotArrayTile"):
        assert tab_item not in src, (
            f"engine draw_plans names tab item class {tab_item!r} "
            f"(engine never names its callers)"
        )
    for rx in _FORBIDDEN_TEXT_RES:
        assert not rx.search(src), (
            f"engine draw_plans matches app-layer literal {rx.pattern!r}"
        )
    tree = _parse(ENGINE_DRAW_PLANS)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            top = node.module.split(".")[0]
            assert top in ("__future__", "collections", "dataclasses", "engine"), (
                f"engine draw_plans imports '{node.module}' (line "
                f"{node.lineno}): engine + stdlib only"
            )


def test_no_second_draw_plan_builders():
    definers: dict[str, set[str]] = {}
    for name in (
        "build_compare_pair_plan",
        "build_array_draw_plan",
        "build_slot_draw_plan",
        "build_slot_array_tiles",
    ):
        definers[name] = set()
    for path in iter_py(ROOT / "src"):
        if "__pycache__" in path.parts:
            continue
        tree = parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in definers:
                    definers[node.name].add(rel(path))
    assert definers["build_compare_pair_plan"] == {
        "src/engine/cache/draw_plans.py"
    }, f"pair builder must have exactly one home: {definers['build_compare_pair_plan']}"
    assert definers["build_array_draw_plan"] == {
        "src/tabs/image_compare/canvas/rhi_renderer/draw_plan.py"
    }, f"IC builder second copy: {definers['build_array_draw_plan']}"
    assert definers["build_slot_draw_plan"] == {
        "src/tabs/multi_compare/scene/tile_geometry.py"
    }, f"MC draw-plan second copy: {definers['build_slot_draw_plan']}"
    assert definers["build_slot_array_tiles"] == {
        "src/tabs/multi_compare/scene/tile_geometry.py"
    }, f"MC array-tiles second copy: {definers['build_slot_array_tiles']}"
    # drop_covered_fallback_tiles has exactly two homes by design: the
    # engine rect-level implementation plus the tab tile<->rect adapter.
    drop_homes = set()
    for path in iter_py(ROOT / "src"):
        if "__pycache__" in path.parts:
            continue
        tree = parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "drop_covered_fallback_tiles"
            ):
                drop_homes.add(rel(path))
    assert drop_homes == {
        "src/engine/cache/draw_plans.py",
        "src/tabs/multi_compare/scene/tile_geometry.py",
    }, f"drop_covered homes drifted (engine impl + tab adapter only): {drop_homes}"


def test_ic_draw_plan_is_thin_adapter():
    tree = _parse(IC_DRAW_PLAN)
    defined = _defined_names(tree)
    assert not (defined & _TAB_FORBIDDEN_DEFS), (
        f"IC draw_plan re-defines moved math: {sorted(defined & _TAB_FORBIDDEN_DEFS)} "
        f"(lift-then-delete: the engine module is the single home)"
    )
    calls = _call_names_in(tree)
    assert not (calls & _TAB_FORBIDDEN_CALLS), (
        f"IC draw_plan still calls moved math: {sorted(calls & _TAB_FORBIDDEN_CALLS)}"
    )
    assert "build_compare_pair_plan" in calls, (
        "IC build_array_draw_plan must call the engine pair builder"
    )
    assert "slot_for" in calls, (
        "IC adapter must keep the slot_for residency filter at the call "
        "surface (test_coverage_uses_slot_for pin)"
    )


def test_mc_tile_geometry_is_thin_adapter():
    tree = _parse(MC_TILE_GEOMETRY)
    defined = _defined_names(tree)
    assert not ((defined - {"_visible_slot_image_rect"}) & _TAB_FORBIDDEN_DEFS), (
        f"MC tile_geometry re-defines moved math: "
        f"{sorted((defined - {'_visible_slot_image_rect'}) & _TAB_FORBIDDEN_DEFS)}"
    )
    calls = _call_names_in(tree)
    assert not (calls & _TAB_FORBIDDEN_CALLS), (
        f"MC tile_geometry still calls moved math: "
        f"{sorted(calls & _TAB_FORBIDDEN_CALLS)}"
    )
    assert "build_slot_plan_tiles" in calls, (
        "MC builders must call the engine slot builder"
    )
    assert "drop_covered_fallback_tiles" in calls, (
        "MC drop adapter must call the engine rect-level drop"
    )


def test_mc_visible_rect_stays_a_delegate():
    seg = _function_segment(MC_TILE_GEOMETRY, "_visible_slot_image_rect")
    assert "slot_visible_rect" in seg, (
        "_visible_slot_image_rect must delegate to the engine derivation "
        "(residency-spec pass imports this name; math lives engine-side)"
    )
    tree = ast.parse(seg)
    assert not any(isinstance(node, ast.BinOp) for node in ast.walk(tree)), (
        "_visible_slot_image_rect must forward without arithmetic of its own"
    )


def test_mc_prepare_array_plan_adapts_at_surface():
    seg = _function_segment(MC_BASE_IMAGES, "_prepare_array_plan")
    for pinned in (
        "build_slot_array_tiles",
        "drop_covered_fallback_tiles",
        "resolve_frame_fallback",
        "content_scale_for",
    ):
        assert pinned in seg, (
            f"_prepare_array_plan no longer routes through {pinned!r} "
            f"(engine-backed builders + engine content-scale)"
        )
