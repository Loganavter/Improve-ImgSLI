# Audit-Meta: pattern=state-machine reason="single draw plan builder for RHI renderer"
from __future__ import annotations

from dataclasses import dataclass

from engine.cache import tile_coverage
from engine.cache.tile_coverage import (
    intersection_rect,
    rects_overlap,
    to_common_space,
)
from engine.cache.tile_debug import log_tile_event, tile_dump_enabled
from engine.cache.tile_texture_service import TileTextureService
from engine.frame.context import FrameContext, make_ids
from tabs.image_compare.canvas.loupe_trace import throttle_emit as _throttle_emit

# Backward-compat re-exports: ``renderer.py`` and the IC render tests
# import these underscore names from this module and are outside C1's
# scope, so the names must keep resolving here. They are plain aliases of
# the engine functions -- no local math. New code imports the engine
# names directly from ``engine.cache.tile_coverage``.
_covered_fraction = tile_coverage.covered_fraction
_to_common_space = tile_coverage.to_common_space

from ..texture_parts.tile_geometry import (
    best_tile_overlap_index,
    iter_visible_side_tiles,
    tile_content_scale,
)
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


def _best_diff_tile_index(
    grid, rect1: tuple[float, float, float, float]
) -> tuple[int, int] | None:
    """Shared overlap-pick core of ``_resolve_diff_tile_key``/
    ``_resolve_diff_tile_index`` -- see the former's docstring for why a
    best-pixel-overlap pick (rather than an exact match) is correct here."""
    return best_tile_overlap_index(grid, rect1)


def _resolve_diff_tile_index(
    tile_service: TileTextureService,
    diff_key: object,
    rect1: tuple[float, float, float, float],
) -> tuple[object, tuple[int, int]]:
    """Array-path counterpart of ``_resolve_diff_tile_key``: returns
    ``(source_id, index)`` instead of a tile_key, since the array path looks
    up slots/content-scale via ``tile_service.slot_for``/``content_size_for``
    directly rather than through a GPU texture dict keyed by tile_key."""
    grid = tile_service.grid_for(diff_key)
    if grid is None:
        return diff_key, (0, 0)
    if grid.rows == 1 and grid.columns == 1:
        return diff_key, (0, 0)
    best_index = _best_diff_tile_index(grid, rect1)
    return diff_key, (best_index if best_index is not None else (0, 0))


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


def _content_scale(content_size: tuple[int, int] | None) -> tuple[float, float]:
    return tile_content_scale(content_size, _ARRAY_LAYER_PX)


def _array_side_tiles(
    tile_service: TileTextureService,
    key: object,
    letterbox: tuple[float, float, float, float],
    base_image,
    *,
    viewport_zoom: tuple[float, float] | None = None,
    viewport_offset: tuple[float, float] | None = None,
) -> list[tuple[object, tuple[float, float, float, float], tuple[int, int]]]:
    """Returns every visible tile of one side, each with its own ``(row,
    col)`` index (needed to look up its array slot/content-scale) --
    including a still-1x1 side, which uploads into the array too (see
    ``resources.py``'s ``realize_tile_plan``), so its one tile needs the
    same index-based slot lookup as any other.

    Thin alias over ``texture_parts.tile_geometry.iter_visible_side_tiles``
    (the single enumeration the residency pass agrees on); kept under this
    name so the pairing loop below reads in this module's own terms."""
    return iter_visible_side_tiles(
        tile_service,
        key,
        letterbox,
        base_image,
        viewport_zoom=viewport_zoom,
        viewport_offset=viewport_offset,
    )


def drop_covered_fallback_items(
    fallback_items: list[ArrayDrawItem],
    current_items: list[ArrayDrawItem],
    base_image,
) -> list[ArrayDrawItem]:
    """Tab-side adapter over the engine coverage filter.

    Extracts each item's side-1/side-2 own-image-fraction rects plus the
    two side letterboxes and delegates the keep/drop decision to
    ``engine.cache.tile_coverage`` (shared on-screen mapping with
    ``to_common_space``, per-side ``covered_fraction`` point sampling at
    the engine threshold, both-sides-must-cover rule), then maps the kept
    indices back to items. No coverage math of its own remains here --
    behavior is bit-for-bit the previous inline body, only the home of
    the algorithm changed.

    Kept under this name/signature (rather than calling the engine
    function directly at every use) because ``use_cases/fallback.py``,
    ``renderer.py``, and the IC render tests import it from this module.
    """
    if not current_items:
        return fallback_items
    letterbox1 = tuple(base_image.letterbox1)
    letterbox2 = tuple(base_image.letterbox2)
    kept_indices = tile_coverage.drop_covered_fallback_items(
        [(item.rect1, item.rect2) for item in fallback_items],
        [(item.rect1, item.rect2) for item in current_items],
        letterbox1,
        letterbox2,
    )
    return [fallback_items[index] for index in kept_indices]


def build_array_draw_plan(
    tile_service: TileTextureService,
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
    eviction/upload catches up."""

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
    side1 = _array_side_tiles(
        tile_service,
        texture_keys[0],
        letterboxes[0],
        base_image,
        viewport_zoom=viewport_zoom,
        viewport_offset=viewport_offset,
    )
    side2 = _array_side_tiles(
        tile_service,
        texture_keys[1],
        letterboxes[1],
        base_image,
        viewport_zoom=viewport_zoom,
        viewport_offset=viewport_offset,
    )
    if not side1 or not side2:
        _record_draw_plan_fact([])
        return []
    side2_common = [
        (src2, rect2, idx2, to_common_space(rect2, letterboxes[1]))
        for src2, rect2, idx2 in side2
    ]
    # diff (e.g. the SSIM map) is generated at image1's resolution and
    # aligned with it, so it shares letterbox1 for common-space conversion.
    # It's resolved to its OWN multi-tile set here -- same as side1/side2 --
    # rather than picking one "best overlap" diff tile per (side1, side2)
    # pair: when diff's grid is finer than side1's (e.g. side1 dropped to a
    # coarse pyramid level while zoomed out but diff has no matching coarse
    # level of its own), a single-tile pick means only as many distinct diff
    # tiles as side1 has instances ever get shown, each stretched over a
    # whole side1 tile's footprint -- a coarse, blocky mosaic instead of
    # diff's real per-tile content (see docs/dev/rendering/qrhi-gotchas.md
    # #magnifier-content-detaches-from-its-own-border-on-zoom-pan sibling
    # investigation notes on this same session's SSIM canvas display bug).
    # Each entry is (diff_src, diff_idx, diff_rect_raw, diff_common):
    # ``diff_rect_raw`` is diff's own image-fraction rect (the same
    # reference frame as rect1/rect2/sampleUV -- passed to the shader
    # as-is, unlike bbox which is common-space); ``diff_common`` is that
    # same rect mapped into common/canvas space (side1's letterbox) only
    # for this function's own overlap/bbox-clipping math against
    # pair_bbox. Conflating the two into a single common-space value here
    # used to feed the shader a rect in the wrong coordinate space for
    # subtracting from sampleUV, which is raw-image-fraction like
    # rect1/rect2, not common-space.
    diff_tiles_common: list[
        tuple[
            object,
            tuple[int, int],
            tuple[float, float, float, float],
            tuple[float, float, float, float],
        ]
    ] = []
    diff_is_multi_tile = False
    if diff_key is not None:
        diff_grid = tile_service.grid_for(diff_key)
        diff_is_multi_tile = diff_grid is not None and not (
            diff_grid.rows == 1 and diff_grid.columns == 1
        )
        if diff_is_multi_tile:
            diff_tiles_common = [
                (
                    diff_src,
                    diff_idx,
                    diff_rect,
                    to_common_space(diff_rect, letterboxes[0]),
                )
                for diff_src, diff_rect, diff_idx in _array_side_tiles(
                    tile_service,
                    diff_key,
                    letterboxes[0],
                    base_image,
                    viewport_zoom=viewport_zoom,
                    viewport_offset=viewport_offset,
                )
            ]
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
            diff_tiles_common=len(diff_tiles_common),
        )
    items: list[ArrayDrawItem] = []
    for src1, rect1, idx1 in side1:
        slot1 = tile_service.slot_for(src1, idx1)
        if slot1 is None:
            continue
        array_index1, layer1 = slot1
        scale1 = _content_scale(tile_service.content_size_for(src1, idx1))
        fallback_diff_layer, fallback_diff_scale = 0, (1.0, 1.0)
        if diff_key is not None and not diff_is_multi_tile:
            # Single-tile (or not-yet-registered) diff: same one-lookup
            # behavior as before, no multi-instance split needed. A
            # genuinely multi-tile diff grid with nothing currently visible
            # (diff_tiles_common empty but diff_is_multi_tile true) instead
            # falls through to the split path below, which correctly draws
            # blank diff there rather than reusing this single-tile lookup
            # against a grid it was never valid for.
            diff_src, diff_idx = _resolve_diff_tile_index(tile_service, diff_key, rect1)
            diff_slot = tile_service.slot_for(diff_src, diff_idx)
            if diff_slot is not None and diff_slot[0] == array_index1:
                fallback_diff_layer = diff_slot[1]
                fallback_diff_scale = _content_scale(
                    tile_service.content_size_for(diff_src, diff_idx)
                )
        common1 = to_common_space(rect1, letterboxes[0])
        for src2, rect2, idx2, common2 in side2_common:
            if not rects_overlap(common1, common2):
                continue
            slot2 = tile_service.slot_for(src2, idx2)
            if slot2 is None:
                continue
            array_index2, layer2 = slot2
            if array_index2 != array_index1:
                continue
            scale2 = _content_scale(tile_service.content_size_for(src2, idx2))
            pair_bbox = intersection_rect(common1, common2)
            # Filter floating-point seam slivers: intersection <2px (0.0012*1654)
            # is not real coverage — otherwise 28/49 entries are 0.0007 wide
            # and produce blank middle strip even though covered=1.0. Apron
            # overlap (8px → 0.004*letterbox) stays >0.002 and is kept.
            if pair_bbox[2] < 0.002 or pair_bbox[3] < 0.002:
                continue
            # Micro-gap fix: adjacent tile bboxes share an edge in content
            # space (0.0887 vs 0.08906). Floating-point + integer-rounded
            # letterbox (eager_envelope ux_i/cw) leaves a 0.5-1px screen seam
            # at overview zoom (0.207*0.002*2153≈0.9px) that heals after any
            # zoom recomputes letterbox/visible_rect. Expand bbox by ~1px
            # screen (≈0.003 in content space at overview) to guarantee
            # overlap and no background bleed. Clamp to [0,1] so we never
            # sample outside the letterbox. Must be after the <0.002 sliver
            # filter or 0.0007 slivers would be inflated to 0.0037 and kept.
            _eps = 0.003
            pair_bbox = (
                max(0.0, pair_bbox[0] - _eps),
                max(0.0, pair_bbox[1] - _eps),
                min(1.0 - max(0.0, pair_bbox[0] - _eps), pair_bbox[2] + 2 * _eps),
                min(1.0 - max(0.0, pair_bbox[1] - _eps), pair_bbox[3] + 2 * _eps),
            )
            content_scale = (*scale1, *scale2)
            if not diff_is_multi_tile:
                items.append(
                    ArrayDrawItem(
                        rect1=rect1,
                        rect2=rect2,
                        content_scale=content_scale,
                        content_scale_diff=fallback_diff_scale,
                        layer1=layer1,
                        layer2=layer2,
                        layer_diff=fallback_diff_layer,
                        array_index=array_index1,
                        sampler_name=sampler_name,
                        bbox=pair_bbox,
                    )
                )
                continue
            emitted_for_pair = False
            for diff_src, diff_idx, diff_rect_raw, diff_common in diff_tiles_common:
                if not rects_overlap(pair_bbox, diff_common):
                    continue
                diff_slot = tile_service.slot_for(diff_src, diff_idx)
                if diff_slot is None or diff_slot[0] != array_index1:
                    continue
                _diff_bbox = intersection_rect(pair_bbox, diff_common)
                if _diff_bbox[2] < 0.002 or _diff_bbox[3] < 0.002:
                    continue
                _diff_bbox = (
                    max(0.0, _diff_bbox[0] - _eps),
                    max(0.0, _diff_bbox[1] - _eps),
                    min(1.0 - max(0.0, _diff_bbox[0] - _eps), _diff_bbox[2] + 2 * _eps),
                    min(1.0 - max(0.0, _diff_bbox[1] - _eps), _diff_bbox[3] + 2 * _eps),
                )
                emitted_for_pair = True
                items.append(
                    ArrayDrawItem(
                        rect1=rect1,
                        rect2=rect2,
                        content_scale=content_scale,
                        content_scale_diff=_content_scale(
                            tile_service.content_size_for(diff_src, diff_idx)
                        ),
                        layer1=layer1,
                        layer2=layer2,
                        layer_diff=diff_slot[1],
                        array_index=array_index1,
                        sampler_name=sampler_name,
                        bbox=_diff_bbox,
                        rect_diff=diff_rect_raw,
                    )
                )
            if not emitted_for_pair:
                # No resident diff tile covers this pair's footprint yet
                # (still uploading) -- draw the base images anyway rather
                # than lose them for this frame; diff shows blank there
                # until its tile arrives.
                items.append(
                    ArrayDrawItem(
                        rect1=rect1,
                        rect2=rect2,
                        content_scale=content_scale,
                        content_scale_diff=(1.0, 1.0),
                        layer1=layer1,
                        layer2=layer2,
                        layer_diff=0,
                        array_index=array_index1,
                        sampler_name=sampler_name,
                        bbox=pair_bbox,
                    )
                )
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
