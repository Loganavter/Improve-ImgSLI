"""Fallback coverage is computed only over actually-resident tiles.

Rule going forward (docs/dev/rendering/tile-rendering-system.md
"Fallback-LOD"): any "is this old content already replaced" coverage check
must be computed against ``tile_service.slot_for(...) is not None`` (or an
equivalent actual-residency check), never against a draw-plan/geometry
pass's target/visible tile list. A freshly-registered key's grid is
visible-but-empty until the budgeted upload loop lands it, so feeding the
geometrically-visible list into the coverage check drops every fallback
tile on the first frame — the blank-hole flash the mechanism exists to
prevent.

This pins the invariant at every current seam:

* image_compare filters inside ``build_array_draw_plan``'s own pairing loop
  (``slot_for`` guard per side + diff), so ``current_array_plan`` — and the
  fallback items rebuilt through the same function — can never contain a
  non-resident item;
* multi_compare filters ``build_slot_array_tiles`` output to
  ``slot_for(...) is not None`` at construction for both the current and
  the fallback set (``BaseImagesPass._prepare_array_plan``);
* the ``drop_covered_fallback_*`` callees are pure over their inputs (no
  residency lookup of their own that could smuggle an unfiltered path in);
* the set of coverage-consumer files is fixed — a new call site forces a
  deliberate test update plus a residency-filter review.

Dogma source: task-engine-1a-seal-2026-09-14 (Engine W1A: seal),
invariant (b).
"""

from __future__ import annotations

import ast

from ._framework import ROOT, iter_py, parse, rel

IC_DRAW_PLAN = ROOT / "src/tabs/image_compare/canvas/rhi_renderer/draw_plan.py"
ENGINE_COVERAGE = ROOT / "src/engine/cache/tile_coverage.py"
IC_FALLBACK = (
    ROOT / "src/tabs/image_compare/canvas/rhi_renderer/use_cases/fallback.py"
)
IC_COVERAGE = (
    ROOT / "src/tabs/image_compare/canvas/rhi_renderer/use_cases/coverage.py"
)
MC_TILE_GEOMETRY = ROOT / "src/tabs/multi_compare/scene/tile_geometry.py"
MC_BASE_IMAGES = ROOT / "src/tabs/multi_compare/scene/passes/base_images.py"

_COVERAGE_CALL_NAMES = frozenset(
    {
        "drop_covered_fallback_items",
        "drop_covered_fallback_tiles",
        "resolve_fallback_lod",
        "covered_fraction",
        "_covered_fraction",
    }
)


def _function_segment(path, func_name: str) -> str:
    text = path.read_text(encoding="utf-8")
    tree = parse(path)
    assert tree is not None, f"unparsable {path}"
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == func_name
        ):
            seg = ast.get_source_segment(text, node)
            assert seg is not None, f"{rel(path)}:{node.lineno} no source segment"
            return seg
    raise AssertionError(f"{rel(path)}: no function {func_name!r}")


def test_ic_pairing_loop_filters_nonresident_tiles():
    seg = _function_segment(IC_DRAW_PLAN, "build_array_draw_plan")
    guards = seg.count("slot_for(")
    assert guards >= 3, (
        f"build_array_draw_plan has {guards} slot_for( lookups, expected "
        f">= 3 (side1, side2, diff) — the pairing loop must skip any tile "
        f"with no array slot yet"
    )
    assert seg.count("is None") >= 3, (
        "build_array_draw_plan lost its `slot ... is None: continue` guards — "
        "non-resident tiles would reach the coverage check"
    )


def test_mc_prepare_array_plan_filters_current_and_fallback():
    seg = _function_segment(MC_BASE_IMAGES, "_prepare_array_plan")
    assert "build_slot_array_tiles" in seg, (
        "_prepare_array_plan no longer builds from build_slot_array_tiles"
    )
    for pinned in (
        "if tile_service.slot_for(key, tile.index) is not None",
        "if tile_service.slot_for(prior_key, tile.index) is not None",
    ):
        assert pinned in seg, (
            f"_prepare_array_plan lost its residency filter {pinned!r} — "
            f"coverage would be computed over non-resident tiles"
        )


def test_drop_functions_are_pure_over_caller_supplied_lists():
    # Phase F flag-day: the tab adapter is deleted, the single home is
    # engine.cache.tile_coverage (sole caller: use_cases/fallback.py).
    for path, func in (
        (ENGINE_COVERAGE, "drop_covered_fallback_items"),
        (MC_TILE_GEOMETRY, "drop_covered_fallback_tiles"),
    ):
        seg = _function_segment(path, func)
        assert "covered_fraction" in seg, (
            f"{rel(path)}::{func} no longer computes coverage"
        )
        for smuggled in (
            "slot_for(",
            "grid_for(",
            "visible_tiles(",
            "build_slot_array_tiles(",
            "build_array_draw_plan(",
        ):
            assert smuggled not in seg, (
                f"{rel(path)}::{func} performs its own {smuggled!r} lookup — "
                f"coverage inputs must arrive pre-filtered from the caller, "
                f"the callee must stay pure"
            )


def _call_names_in(path) -> set[str]:
    tree = parse(path)
    if tree is None:
        return set()
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


def test_coverage_consumers_are_exactly_the_known_set():
    # Phase F flag-day: draw_plan.py no longer names coverage calls (the
    # tab adapter + re-exports were deleted; the pairing loop calls
    # to_common_space/rects_overlap/intersection_rect directly, which are
    # geometry -- not coverage -- call names). Sole drop_covered caller
    # is use_cases/fallback.py (engine home).
    expected = {
        rel(IC_COVERAGE),
        rel(IC_FALLBACK),
        rel(MC_TILE_GEOMETRY),
        rel(MC_BASE_IMAGES),
    }
    actual = {
        rel(py)
        for py in iter_py(ROOT / "src" / "tabs")
        if _call_names_in(py) & _COVERAGE_CALL_NAMES
    }
    assert actual == expected, (
        "coverage-consumer set drifted:\n"
        f"  added: {sorted(actual - expected)}\n"
        f"  removed: {sorted(expected - actual)}\n"
        "a new call site must prove its inputs are slot_for-filtered "
        "before joining this set"
    )
