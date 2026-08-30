# Audit-Meta: pattern=state-machine reason="single draw plan builder for RHI renderer"
from __future__ import annotations

from dataclasses import dataclass

from shared.image_processing.pyramid_registry import pyramid_for
from shared.image_processing.tiled_pixel_store import TiledPixelStore
from shared.rendering.lod import LevelKey, select_level
from shared.rendering.tile_coverage import (
    FALLBACK_COVERAGE_THRESHOLD as _FALLBACK_COVERAGE_THRESHOLD,
    covered_fraction as _covered_fraction,
    intersection_rect as _intersection_rect,
    rects_overlap as _rects_overlap,
    to_common_space as _to_common_space,
)
from shared.rendering.tile_debug import log_tile_event, tile_dump_enabled
from shared.rendering.tile_texture_service import TileTextureService

from ..texture_parts.tile_geometry import _apron_rect, _TILE_APRON_PX, _visible_side_image_rect
from .resources import _ARRAY_LAYER_PX
from .uniforms import _FULL_TILE_RECT
from ._debug import rhi_render_debug


def resolve_lod_texture_keys(
    texture_keys: tuple[object, object],
    sources: tuple[object, object],
    base_image,
    canvas_size_px: tuple[float, float],
) -> tuple[object, object]:
    """Substitutes each side's texture key with a ``LevelKey`` for the
    pyramid mipmap level matching the current on-screen scale.

    ``canvas_size_px`` is the full logical canvas in *device* pixels (live:
    widget size x DPR; tiled export: the whole export canvas), so live
    render, snapshot and export resolve identical levels for the same
    document+zoom (rendering-model.md parity). Per-tile export zoom is
    deliberately not used here — all tiles of one export must sample one
    level or seams appear. Sides without a registered pyramid (plain PIL,
    preview tier, pyramid not yet built/invalidated) keep their bare key,
    which is byte-identical to the pre-pyramid path."""
    canvas_w_px, canvas_h_px = canvas_size_px
    zoom = float(base_image.zoom) or 1.0
    letterboxes = (base_image.letterbox1, base_image.letterbox2)
    pyramids = [
        pyramid_for(source) if isinstance(source, TiledPixelStore) else None
        for source in sources
    ]
    # Both sides' pyramids build their levels asynchronously in the
    # background and can finish a level at different times. Clamping each
    # side to its own pyramid.level_count independently (as
    # best_level_for_scale does) lets one side pick a level the other
    # hasn't built yet whenever both are multi-tile -- their tile rects are
    # fractions of that side's own grid dimensions, which are only
    # comparable between sides when both grids have the same row/column
    # count. A shared level_count cap keeps both sides' clamped level (and
    # thus grid dimensions) identical whenever they'd otherwise want the
    # same level (the common case, since compared images are unified to
    # matching sizes/letterboxes).
    # While one side's pyramid is still building (or the side is a
    # preview QImage with no pyramid at all) the two sides' grids differ:
    # bare 2796 is 6×5 tiles, LevelKey(1) 1398 is 3×3, preview is 1×1.
    # _to_common_space/bbox then collapses to a 0.001 sliver even though
    # each side's own rect coverage is 1.0, producing a blank middle strip.
    # Keep both sides at level 0 until every TiledPixelStore side has a
    # pyramid, so fallback-LOD's atomic hold keeps the old matched content
    # instead of promoting a mismatched-grid plan.
    tiled_sources = [s for s in sources if isinstance(s, TiledPixelStore)]
    tiled_pyramids = [pyramid_for(s) for s in tiled_sources]
    if tiled_sources and any(p is None for p in tiled_pyramids):
        shared_level_count = 0
    else:
        ready_pyramids = [p for p in tiled_pyramids if p is not None]
        shared_level_count = (
            min(p.level_count for p in ready_pyramids) if ready_pyramids else 0
        )
    resolved = []
    for key, letterbox, source, pyramid in zip(
        texture_keys, letterboxes, sources, pyramids
    ):
        if not isinstance(source, TiledPixelStore):
            resolved.append(key)
            continue
        if pyramid is None:
            resolved.append(key)
            continue
        src_w, src_h = source.size
        disp_w = canvas_w_px * float(letterbox[2] or 1.0) * zoom
        disp_h = canvas_h_px * float(letterbox[3] or 1.0) * zoom
        dest_scale = max(
            disp_w / float(max(1, src_w)), disp_h / float(max(1, src_h))
        )
        level = select_level(dest_scale, shared_level_count)
        rhi_render_debug(
            "resolve_lod key=%s use_hires=%s zoom=%.3f src=%dx%d disp=%.1fx%.1f "
            "dest_scale=%.5f level=%d/%d",
            key,
            getattr(base_image, "use_hires", None),
            zoom,
            src_w,
            src_h,
            disp_w,
            disp_h,
            dest_scale,
            level,
            pyramid.level_count - 1,
        )
        resolved.append(key if level == 0 else LevelKey(key, level))
    return tuple(resolved)  # type: ignore[return-value]  # tuple of key|LevelKey


def _best_diff_tile_index(
    grid, rect1: tuple[float, float, float, float]
) -> tuple[int, int] | None:
    """Shared overlap-pick core of ``_resolve_diff_tile_key``/
    ``_resolve_diff_tile_index`` -- see the former's docstring for why a
    best-pixel-overlap pick (rather than an exact match) is correct here."""
    left_f, top_f, width_f, height_f = rect1
    left = left_f * grid.total_width
    top = top_f * grid.total_height
    right = (left_f + width_f) * grid.total_width
    bottom = (top_f + height_f) * grid.total_height
    best_index = None
    best_overlap = -1.0
    for row, col, region in grid.iter_regions():
        overlap_w = max(0.0, min(right, region.right) - max(left, region.left))
        overlap_h = max(0.0, min(bottom, region.bottom) - max(top, region.top))
        overlap = overlap_w * overlap_h
        if overlap > best_overlap:
            best_overlap = overlap
            best_index = (row, col)
    return best_index


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
    if content_size is None:
        return (1.0, 1.0)
    width, height = content_size
    return (width / _ARRAY_LAYER_PX, height / _ARRAY_LAYER_PX)


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
    same index-based slot lookup as any other."""
    grid = tile_service.grid_for(key)
    if grid is None:
        return [(key, _FULL_TILE_RECT, (0, 0))]
    visible_rect = _visible_side_image_rect(
        base_image,
        letterbox,
        grid,
        viewport_zoom=viewport_zoom,
        viewport_offset=viewport_offset,
    )
    visible_indices = tile_service.visible_tiles(key, visible_rect)
    side_tiles = []
    for row, col, region in grid.iter_regions():
        if (row, col) not in visible_indices:
            continue
        left, top, right, bottom = _apron_rect(
            grid.total_width, grid.total_height, region, _TILE_APRON_PX
        )
        rect = (
            left / grid.total_width,
            top / grid.total_height,
            (right - left) / grid.total_width,
            (bottom - top) / grid.total_height,
        )
        side_tiles.append((key, rect, (row, col)))
    return side_tiles


def drop_covered_fallback_items(
    fallback_items: list[ArrayDrawItem],
    current_items: list[ArrayDrawItem],
    base_image,
) -> list[ArrayDrawItem]:
    """Drops fallback-LOD items whose on-screen footprint is already fully
    covered by the current level's (possibly partial) draw plan, leaving
    only the still-missing regions of the old level to draw underneath.

    Before this filter, ``render()``'s ``has_fallback`` branch drew the
    *entire* previous level's tile set plus the current level's every frame
    for the whole duration of a transition (bounded by
    ``TILE_UPLOAD_TIME_BUDGET_MS``, which can span many frames for a large
    pyramid). RenderDoc profiling of a 20k-source LOD transition showed this
    summing to a 133-instance ``glDrawArraysInstanced`` costing ~36ms/frame
    on GPU -- roughly double the steady-state instance count -- which
    scales with how many tiles are visible on screen at once, i.e. worse for
    large sources than small ones (docs/dev/rendering/
    tile-array-atlas-plan.md Phase 8).

    A region only counts as covered if *both* sides have a current-level
    item there, not just image1 -- side1 and side2 upload independently
    (their own budget/time-deadline accounting in ``realize_tile_plan`` is
    entirely separate), so it's common for one side to finish uploading a
    LOD level's full tile set several frames before the other. Checking
    ``rect1`` alone (as this used to) meant a screen region got dropped from
    the fallback the moment image1's new-level tile arrived there, even
    though image2 in that same region might still be many tiles away from
    ready -- image2 then had no fallback tile to fall through to and no
    current one either, i.e. a real blank/missing-image gap on every
    single-step LOD transition where the two sides don't finish in
    lockstep (docs/dev/rendering/tile-array-atlas-plan.md Phase 9 "clear/
    fill/draw cycle visible on one zoom step" finding).

    Coverage is an area fraction (``_covered_fraction``/
    ``_FALLBACK_COVERAGE_THRESHOLD``), not a boolean any-overlap test: the
    fallback level and the current level are different pyramid levels with
    different grid dimensions, so one coarse old tile's footprint typically
    spans *several* fine new tiles. A plain "do these two rects overlap at
    all" check (this function's original form) dropped the whole coarse
    tile the instant the very first of those several new tiles arrived,
    even though most of its footprint was still unreplaced -- exactly the
    fallback_raw=49/fallback_entries=0 case from the finding above, where
    image1 alone reaching 100% residency was enough to zero out the entire
    fallback plan although image2 was nowhere near done."""
    if not current_items:
        return fallback_items
    letterbox1 = tuple(base_image.letterbox1)
    letterbox2 = tuple(base_image.letterbox2)
    current_common1 = [
        _to_common_space(item.rect1, letterbox1) for item in current_items
    ]
    current_common2 = [
        _to_common_space(item.rect2, letterbox2) for item in current_items
    ]
    kept = []
    for item in fallback_items:
        common1 = _to_common_space(item.rect1, letterbox1)
        common2 = _to_common_space(item.rect2, letterbox2)
        covered1 = _covered_fraction(common1, current_common1)
        covered2 = _covered_fraction(common2, current_common2)
        if (
            covered1 >= _FALLBACK_COVERAGE_THRESHOLD
            and covered2 >= _FALLBACK_COVERAGE_THRESHOLD
        ):
            continue
        kept.append(item)
    return kept


def build_array_draw_plan(
    tile_service: TileTextureService,
    texture_keys: tuple[object, object],
    base_image,
    *,
    diff_key: object | None,
    sampler_name: str,
    viewport_zoom: tuple[float, float] | None = None,
    viewport_offset: tuple[float, float] | None = None,
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
        return []
    side2_common = [
        (src2, rect2, idx2, _to_common_space(rect2, letterboxes[1]))
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
                    _to_common_space(diff_rect, letterboxes[0]),
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
        common1 = _to_common_space(rect1, letterboxes[0])
        for src2, rect2, idx2, common2 in side2_common:
            if not _rects_overlap(common1, common2):
                continue
            slot2 = tile_service.slot_for(src2, idx2)
            if slot2 is None:
                continue
            array_index2, layer2 = slot2
            if array_index2 != array_index1:
                continue
            scale2 = _content_scale(tile_service.content_size_for(src2, idx2))
            pair_bbox = _intersection_rect(common1, common2)
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
                if not _rects_overlap(pair_bbox, diff_common):
                    continue
                diff_slot = tile_service.slot_for(diff_src, diff_idx)
                if diff_slot is None or diff_slot[0] != array_index1:
                    continue
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
                        bbox=_intersection_rect(pair_bbox, diff_common),
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
    return items
