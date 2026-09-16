# Audit-Meta: pattern=state-machine reason="single draw plan builder for RHI renderer"
from __future__ import annotations

from dataclasses import dataclass

from engine.cache.draw_plans import (
    PlanTile,
    build_compare_pair_plan,
)
from engine.cache.tile_debug import log_tile_event, tile_dump_enabled
from engine.frame.context import FrameContext, make_ids
from tabs.image_compare.canvas.loupe_trace import throttle_emit as _throttle_emit

from ..texture_parts.tile_geometry import iter_visible_side_tiles
from .residency import resolve_lod_texture_keys
from .resources import _ARRAY_LAYER_PX

try:
    from tabs.image_compare.debug import ic_gap_debug as _gap_log, ic_gap_debug_enabled as _gap_enabled  # type: ignore
except Exception:  # pragma: no cover

    def _gap_log(msg: str, *a, **kw) -> None:  # type: ignore
        return None

    def _gap_enabled() -> bool:  # type: ignore
        return False


# Sig-throttle for the per-frame gap draw_plan log: build_array_draw_plan
# runs on every frame (including keep-warm no-op ticks), so an unconditional
# log spams identical lines while the sig is unchanged. State lives in
# loupe_trace's centralized throttle store (stream "draw_plan.gap") — same
# pattern as renderer.py's "renderer.draw_plan" stream (texture keys + items
# length + layers + bbox sample). Fallback promotion logging is untouched.


# LOD-key resolution lives in ``residency.py`` (next to the grid
# registration that consumes it -- the BaseImagesPass shape: tab resolves
# specs, engine decides); re-exported here so existing callers
# (``renderer.py``, ``use_cases/lod_commit.py``, tests) keep importing it
# from this module unchanged.


# NOTE (R4 flag-day): draw-plan math (visible-tile enumeration excluded --
# that stays shared with the residency-spec pass via
# ``texture_parts.tile_geometry.iter_visible_side_tiles`` -- plus
# common-space overlap, bbox clipping, diff-tile resolution) lives in
# ``engine.cache.draw_plans``; this module only adapts engine plan structs
# to ``ArrayDrawItem``. No coverage or geometry math remains here.


@dataclass(frozen=True)
class ArrayDrawItem:
    """One instance of the texture-array pipeline's instanced draw (docs/dev/
    rendering/tile-array-atlas-plan.md Phase 2), packed by
    ``resources.pack_array_instance`` into ``base_array.vert``'s per-instance
    vertex attributes."""

    rect1: tuple[float, float, float, float]
    rect2: tuple[float, float, float, float]
    content_scale: tuple[float, float, float, float]
    content_scale_diff: tuple[float, float]
    layer1: int
    layer2: int
    layer_diff: int
    array_index: int
    sampler_name: str
    # Content-space (same space as letterbox1/2/canvasLetterbox) bounding box
    # this instance's geometry is clipped to -- rect1's and rect2's common-
    # space footprints intersected, i.e. the only region base_array.frag's
    # tileUV1/tileUV2 discard could ever let through for this instance. See
    # docs/dev/rendering/tile-array-atlas-plan.md Phase 10 (overdraw fix):
    # before this, every instance's vertex shader emitted a shared
    # fullscreen quad and relied entirely on that per-pixel discard to
    # "clip" down to the visible tile, costing a full framebuffer's worth of
    # fragment shader invocations per instance regardless of how small its
    # actual on-screen footprint was.
    bbox: tuple[float, float, float, float]
    # The diff/SSIM tile this instance samples, in the same content-space as
    # rect1/rect2 -- (0,0,1,1) identity when diff isn't split into multiple
    # tiles (build_array_draw_plan's single-lookup fallback path), otherwise
    # the specific diff tile's own full rect, subtracted from sampleUV in
    # base_array.frag before addressing that tile's array layer. See
    # docs/dev/rendering/qrhi-gotchas.md
    # #ssim-diff-blocky-mosaic-at-coarse-lod.
    rect_diff: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)


def build_array_draw_plan(
    tile_service,
    texture_keys: tuple[object, object],
    base_image,
    *,
    diff_key: object | None,
    sampler_name: str,
    viewport_zoom: tuple[float, float] | None = None,
    viewport_offset: tuple[float, float] | None = None,
    frame_context: FrameContext | None = None,
) -> list[ArrayDrawItem]:
    """Builds the texture-array pipeline's per-instance draw plan: every
    visible (image1 tile, image2 tile) combination whose on-screen
    (letterbox-mapped) rects
    actually overlap, resolved to array slots/content-scale instead of GPU
    texture keys. A pair whose rects don't overlap in shared screen space
    would be fully discarded by ``base_array.frag``'s per-pixel
    ``inTile1``/``inTile2`` check anyway (see that shader) -- filtering
    them here instead avoids submitting draw instances that can only ever
    show a wrong/neighboring tile's content through a stray rounding sliver
    (found as part of the same investigation as the ``_ARRAY_CAPACITY``
    fix in ``resources.py`` -- see docs/dev/rendering/
    tile-array-atlas-plan.md Phase 2 Findings). Skips a pair whose two
    sides ended up in different array textures (only possible if
    _ARRAY_CAPACITY is ever exceeded -- see resources.py) rather than draw
    mismatched content; the dropped pair is retried next frame once
    eviction/upload catches up.

    Thin adapter over ``engine.cache.draw_plans.build_compare_pair_plan``
    (which owns all pairing/bbox/diff math): this function only enumerates
    visible tiles (shared with the residency-spec pass), filters to
    actually-resident tiles, and converts engine plan structs to
    ``ArrayDrawItem``."""

    # ``frame_context`` is the Phase-2 frame-bus hook: when provided, the
    # built plan records its LOD keys + entry count IN ADDITION to existing
    # behavior (``None`` keeps every existing call site behavior-identical).
    def _record_draw_plan_fact(_items: list) -> None:
        """Phase-2 frame-bus write for the draw-plan phase (record only)."""
        if frame_context is not None:
            frame_context.record(
                "build_array_draw_plan",
                "ran" if _items else "skipped",
                "build_array_draw_plan"
                f" entries={len(_items)} sampler={sampler_name}",
                ids=make_ids(
                    frame_context.frame_id,
                    tuple(str(k) for k in texture_keys),
                    len(_items),
                ),
            )

    letterboxes = (tuple(base_image.letterbox1), tuple(base_image.letterbox2))
    raw_side1 = iter_visible_side_tiles(
        tile_service,
        texture_keys[0],
        letterboxes[0],
        base_image,
        viewport_zoom=viewport_zoom,
        viewport_offset=viewport_offset,
    )
    raw_side2 = iter_visible_side_tiles(
        tile_service,
        texture_keys[1],
        letterboxes[1],
        base_image,
        viewport_zoom=viewport_zoom,
        viewport_offset=viewport_offset,
    )
    # Residency-filtered at the point of construction: only actually-
    # resident tiles reach the engine pairing builder (and from there the
    # fallback-coverage check), never the geometrically-visible-but-empty
    # target set -- pinned by tests/contracts/test_coverage_uses_slot_for.py.
    side1: list[PlanTile] = []
    for _raw_key1, _raw_rect1, _raw_idx1 in raw_side1:
        _slot1 = tile_service.slot_for(texture_keys[0], _raw_idx1)
        if _slot1 is None:
            continue
        side1.append(PlanTile(rect=_raw_rect1, index=_raw_idx1))
    side2: list[PlanTile] = []
    for _raw_key2, _raw_rect2, _raw_idx2 in raw_side2:
        _slot2 = tile_service.slot_for(texture_keys[1], _raw_idx2)
        if _slot2 is None:
            continue
        side2.append(PlanTile(rect=_raw_rect2, index=_raw_idx2))
    if not side1 or not side2:
        _record_draw_plan_fact([])
        return []
    # Diff (e.g. the SSIM map) is generated at image1's resolution and
    # aligned with it, so it shares letterbox1 for common-space conversion.
    # Enumerated like any other side; the engine builder decides single- vs
    # multi-tile resolution. Pre-filtered to resident tiles like both sides.
    diff_tiles: list[PlanTile] = []
    if diff_key is not None:
        for _draw_key, _draw_rect, _draw_idx in iter_visible_side_tiles(
            tile_service,
            diff_key,
            letterboxes[0],
            base_image,
            viewport_zoom=viewport_zoom,
            viewport_offset=viewport_offset,
        ):
            _draw_slot = tile_service.slot_for(_draw_key, _draw_idx)
            if _draw_slot is None:
                continue
            diff_tiles.append(PlanTile(rect=_draw_rect, index=_draw_idx))
    if diff_key is not None and tile_dump_enabled():
        side1_grid = tile_service.grid_for(texture_keys[0])
        diff_grid_dbg = tile_service.grid_for(diff_key)
        log_tile_event(
            "array_draw_plan.diff_resolve",
            diff_key=str(diff_key),
            side1_key=str(texture_keys[0]),
            side1_tiles=len(side1),
            side1_grid=(
                f"{side1_grid.rows}x{side1_grid.columns}"
                if side1_grid is not None
                else None
            ),
            diff_grid=(
                f"{diff_grid_dbg.rows}x{diff_grid_dbg.columns}"
                if diff_grid_dbg is not None
                else None
            ),
            diff_tiles_common=len(diff_tiles),
        )
    plans = build_compare_pair_plan(
        tile_service,
        texture_keys[0],
        texture_keys[1],
        letterboxes[0],
        letterboxes[1],
        side1=side1,
        side2=side2,
        diff_key=diff_key,
        diff_tiles=diff_tiles,
        layer_px=_ARRAY_LAYER_PX,
    )
    items = [
        ArrayDrawItem(
            rect1=plan.rect1,
            rect2=plan.rect2,
            content_scale=plan.content_scale,
            content_scale_diff=plan.content_scale_diff,
            layer1=plan.layer1,
            layer2=plan.layer2,
            layer_diff=plan.layer_diff,
            array_index=plan.array_index,
            sampler_name=sampler_name,
            bbox=plan.bbox,
            rect_diff=plan.rect_diff,
        )
        for plan in plans
    ]
    if diff_key is not None and tile_dump_enabled():
        log_tile_event(
            "array_draw_plan.result",
            diff_key=str(diff_key),
            item_count=len(items),
            distinct_diff_layers=len({item.layer_diff for item in items}),
        )
    if _gap_enabled() and items:
        try:
            _gap_sig = (
                tuple(str(k) for k in texture_keys),
                len(items),
                tuple(getattr(it, "layer1", None) for it in items[:3]),
                tuple(getattr(it, "layer2", None) for it in items[:3]),
                tuple(getattr(it, "bbox", None) for it in items[:2]),
            )
            if not _throttle_emit("draw_plan.gap", _gap_sig):
                _record_draw_plan_fact(items)
                return items
        except Exception:
            pass
        try:
            widths = [b[2] for b in (it.bbox for it in items)]
            heights = [b[3] for b in (it.bbox for it in items)]
            widths_sorted = sorted(widths)
            narrow = sum(1 for w in widths if w < 0.01)
            min_w = min(widths) if widths else 0.0
            max_w = max(widths) if widths else 0.0
            med_w = widths_sorted[len(widths_sorted)//2] if widths_sorted else 0.0
            # detect central gap via sorted bbox X gaps
            xs = sorted([it.bbox[0] for it in items])
            max_gap = 0.0
            if len(xs) > 1:
                for i in range(len(xs)-1):
                    gap = xs[i+1] - (xs[i] + widths_sorted[i] if i < len(widths_sorted) else xs[i])
                    # approximate using bbox x + w; use actual bboxes order
                    pass
            _gap_log(
                "gap draw_plan entries=%d side1=%d side2=%d grid1=%s grid2=%s letterbox1=%s letterbox2=%s bbox w min=%.5f med=%.5f max=%.5f narrow<0.01=%d/%.2f",
                len(items),
                len(side1),
                len(side2),
                f"{tile_service.grid_for(texture_keys[0]).rows if tile_service.grid_for(texture_keys[0]) else 1}x{tile_service.grid_for(texture_keys[0]).columns if tile_service.grid_for(texture_keys[0]) else 1}",
                f"{tile_service.grid_for(texture_keys[1]).rows if tile_service.grid_for(texture_keys[1]) else 1}x{tile_service.grid_for(texture_keys[1]).columns if tile_service.grid_for(texture_keys[1]) else 1}",
                tuple(letterboxes[0]),
                tuple(letterboxes[1]),
                min_w,
                med_w,
                max_w,
                narrow,
                narrow/len(widths) if widths else 0.0,
            )
            if narrow > 0 and min_w < 0.005:
                try:
                    from core.tracing.tracer import Tracer as _Tracer
                    if _Tracer.enabled():
                        _Tracer.instance().record("ic.gap.narrow_bbox", f"narrow bbox {narrow}/{len(items)} min {min_w:.5f}", {"narrow": narrow, "min_w": min_w, "med_w": med_w, "entries": len(items)}, caller_skip=1)
                except Exception:
                    pass
        except Exception:
            pass
    _record_draw_plan_fact(items)
    return items
