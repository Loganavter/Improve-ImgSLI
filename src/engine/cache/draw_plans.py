"""Engine-owned draw-plan math for tiled canvas rendering.

Single home for the coverage/geometry math both compare tabs used to carry
in their own draw-plan builders: visible-tile enumeration over a
``UniformTileGrid`` (rect tuples + apron padding), the fixed-pair
cross-product pairing loop (common-space overlap, bbox clipping, sliver
filter, micro-gap expand, per-diff-tile split), best-overlap tile picking,
content-scale derivation, and slot-model fallback-drop filtering.

Operates purely on engine-level types -- rect tuples, ``UniformTileGrid``,
letterboxes, ``TileTextureService`` -- following the ``tile_coverage``
precedent. Callers adapt their own item classes to/from the plan structs
(``PlanTile`` / ``ComparePairPlan``) at the call surface; no caller-side
item class is ever named here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from engine.cache.tile_coverage import (
    FALLBACK_COVERAGE_THRESHOLD,
    covered_fraction,
    intersection_rect,
    rects_overlap,
    to_common_space,
)
from engine.cache.tile_geometry import _TILE_APRON_PX, _apron_rect
from engine.cache.tile_texture_service import TileTextureService

Rect = tuple[float, float, float, float]
TileIndex = tuple[int, int]

#: Full-image fraction rect for a source with no registered grid (the 1x1
#: degenerate case flows through the same code path with a one-element list).
FULL_TILE_RECT: Rect = (0.0, 0.0, 1.0, 1.0)

#: Filter floating-point seam slivers: an intersection narrower than this in
#: either axis is not real coverage (apron overlap stays well above it).
SLIVER_MIN = 0.002

#: Micro-gap fix: adjacent tile bboxes share an edge in content space, but
#: floating-point + integer-rounded letterbox math leaves a sub-pixel screen
#: seam at overview zoom. Bboxes expand by this much (clamped to [0, 1]) to
#: guarantee overlap. Must apply after the sliver filter above, or slivers
#: would be inflated into kept entries.
BBOX_EPS = 0.003


@dataclass(frozen=True)
class PlanTile:
    """One visible tile: its apron-padded image-fraction ``rect`` plus its
    own grid ``index`` (needed to resolve array slots/content sizes)."""

    rect: Rect
    index: TileIndex


@dataclass(frozen=True)
class ComparePairPlan:
    """One fixed-pair draw instance: the two sides' tiles whose on-screen
    (letterbox-mapped) rects overlap, resolved to array slots/content
    scales, clipped to their common-space ``bbox``. ``rect_diff`` is the
    diff tile's own raw image-fraction rect (same space as ``rect1``/
    ``rect2``, not common space) -- identity when diff is single-tile."""

    rect1: Rect
    rect2: Rect
    index1: TileIndex
    index2: TileIndex
    bbox: Rect
    rect_diff: Rect = (0.0, 0.0, 1.0, 1.0)
    layer1: int = 0
    layer2: int = 0
    layer_diff: int = 0
    array_index: int = 0
    content_scale: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    content_scale_diff: tuple[float, float] = (1.0, 1.0)


def slot_visible_rect(
    pan_offset: tuple[float, float],
    fit_scale: tuple[float, float],
    zoom: float,
    grid,
) -> tuple[float, float, float, float]:
    """Currently-visible rect in a slot's tile-grid pixel space.

    Mirrors the slot fragment shader's uv derivation (``fit``/``zoom``/``pan``),
    so viewport-driven tile selection cannot diverge from what is drawn.
    ``zoom`` of ``0`` falls back to ``1.0``; the result is clamped to the
    grid extent.
    """
    zoom = zoom or 1.0
    fit_x = fit_scale[0] or 1.0
    fit_y = fit_scale[1] or 1.0
    pan_x, pan_y = pan_offset
    uv_left = -0.5 / (fit_x * zoom) + 0.5 - pan_x
    uv_right = 0.5 / (fit_x * zoom) + 0.5 - pan_x
    uv_top = -0.5 / (fit_y * zoom) + 0.5 - pan_y
    uv_bottom = 0.5 / (fit_y * zoom) + 0.5 - pan_y
    left = max(0.0, min(1.0, uv_left))
    right = max(0.0, min(1.0, uv_right))
    top = max(0.0, min(1.0, uv_top))
    bottom = max(0.0, min(1.0, uv_bottom))
    return (
        left * grid.total_width,
        top * grid.total_height,
        right * grid.total_width,
        bottom * grid.total_height,
    )


def plan_tiles_for_grid(
    tile_service: TileTextureService,
    source_id: object,
    visible_rect: tuple[float, float, float, float],
    *,
    apron_px: int = _TILE_APRON_PX,
) -> list[PlanTile]:
    """Every tile of ``source_id`` intersecting ``visible_rect``, each with
    its apron-padded image-fraction rect. Driven by the service's visible
    set (sorted row-major), never by scanning the grid. Unregistered sources
    contribute nothing (the 1x1/None shortcuts live in
    ``build_slot_plan_tiles``)."""
    grid = tile_service.grid_for(source_id)
    if grid is None:
        return []
    items: list[PlanTile] = []
    for row, col in sorted(tile_service.visible_tiles(source_id, visible_rect)):
        region = grid.region_for(row, col)
        left, top, right, bottom = _apron_rect(
            grid.total_width, grid.total_height, region, apron_px
        )
        items.append(
            PlanTile(
                rect=(
                    left / grid.total_width,
                    top / grid.total_height,
                    (right - left) / grid.total_width,
                    (bottom - top) / grid.total_height,
                ),
                index=(row, col),
            )
        )
    return items


def build_slot_plan_tiles(
    tile_service: TileTextureService,
    slot_id: object,
    pan_offset: tuple[float, float],
    fit_scale: tuple[float, float],
    zoom: float,
    *,
    apron_px: int = _TILE_APRON_PX,
) -> list[PlanTile]:
    """Array-path slot enumeration: every visible tile's own ``(row, col)``
    index, needed to resolve array slots/content sizes downstream. A slot
    with no registered grid (or a trivial 1x1 grid, which still uploads
    into the shared array) contributes its single whole-image entry, so the
    untiled case flows through the same code path with a degenerate
    one-element list. Never takes an empty shortcut -- an empty visible set
    yields an empty list and the caller decides the fallback."""
    grid = tile_service.grid_for(slot_id)
    if grid is None:
        return [PlanTile(FULL_TILE_RECT, (0, 0))]
    if grid.rows == 1 and grid.columns == 1:
        return [PlanTile(FULL_TILE_RECT, (0, 0))]
    visible_rect = slot_visible_rect(pan_offset, fit_scale, zoom, grid)
    return plan_tiles_for_grid(
        tile_service, slot_id, visible_rect, apron_px=apron_px
    )


def drop_covered_fallback_tiles(
    fallback_rects: Sequence[Rect],
    current_rects: Sequence[Rect],
    *,
    threshold: float = FALLBACK_COVERAGE_THRESHOLD,
) -> list[int]:
    """Indices of ``fallback_rects`` to keep: drops every fallback entry
    whose footprint is already covered by the current level's (possibly
    partial) rects at ``threshold`` (point-sampled ``covered_fraction``).

    Rects are directly comparable fractions of one image (no letterbox to
    map through -- every pyramid level of the same base image shares the
    same 0..1 fraction space). Pure over caller-supplied lists: no residency
    lookup of its own, so the caller must hand in the actually-resident
    subset (never a geometry target list). Empty ``current_rects`` keeps
    every fallback entry.
    """
    if not current_rects:
        return list(range(len(fallback_rects)))
    current = list(current_rects)
    return [
        index
        for index, rect in enumerate(fallback_rects)
        if covered_fraction(rect, current) < threshold
    ]


def best_overlap_tile_index(grid, rect: Rect) -> TileIndex | None:
    """Best-pixel-overlap tile pick for an image-fraction ``rect``: the
    ``(row, col)`` whose region overlaps ``rect`` by the largest pixel area.
    Exact whenever the queried grid matches the live grid (steady state);
    approximate only during transient display downscaling (cosmetic)."""
    left_f, top_f, width_f, height_f = rect
    left = left_f * grid.total_width
    top = top_f * grid.total_height
    right = (left_f + width_f) * grid.total_width
    bottom = (top_f + height_f) * grid.total_height
    query = (left, top, right - left, bottom - top)
    best_index: TileIndex | None = None
    best_overlap = -1.0
    for row, col, region in grid.iter_regions():
        candidate = (
            region.left,
            region.top,
            region.right - region.left,
            region.bottom - region.top,
        )
        if rects_overlap(query, candidate):
            _, _, overlap_w, overlap_h = intersection_rect(query, candidate)
            overlap = overlap_w * overlap_h
        else:
            # Zero-area touch (or no touch at all): same 0.0 the inline
            # max(0, ...) form produced, so degenerate rects keep picking
            # the first iterated region instead of returning None.
            overlap = 0.0
        if overlap > best_overlap:
            best_overlap = overlap
            best_index = (row, col)
    return best_index


def content_scale_for(
    content_size: tuple[int, int] | None, layer_px: float
) -> tuple[float, float]:
    """Per-tile content scale (content px / array-layer px) the shader uses
    to rescale UVs before sampling. ``layer_px`` is passed explicitly (each
    caller owns its array-layer size) so this helper never imports caller
    modules."""
    if content_size is None:
        return (1.0, 1.0)
    width, height = content_size
    return (width / layer_px, height / layer_px)


def _expand_bbox(bbox: Rect, eps: float = BBOX_EPS) -> Rect:
    """Micro-gap expand (see ``BBOX_EPS``): grow ``bbox`` by ``eps`` in
    content space, clamped to [0, 1]."""
    return (
        max(0.0, bbox[0] - eps),
        max(0.0, bbox[1] - eps),
        min(1.0 - max(0.0, bbox[0] - eps), bbox[2] + 2 * eps),
        min(1.0 - max(0.0, bbox[1] - eps), bbox[3] + 2 * eps),
    )


def _resolve_single_diff_index(
    tile_service: TileTextureService, diff_key: object, rect1: Rect
) -> tuple[object, TileIndex]:
    """Array-path diff resolution for a single-tile (or not-yet-registered)
    diff: ``(source_id, index)`` for direct slot/content-size lookup."""
    grid = tile_service.grid_for(diff_key)
    if grid is None:
        return diff_key, (0, 0)
    if grid.rows == 1 and grid.columns == 1:
        return diff_key, (0, 0)
    best_index = best_overlap_tile_index(grid, rect1)
    return diff_key, (best_index if best_index is not None else (0, 0))


def build_compare_pair_plan(
    tile_service: TileTextureService,
    key1: object,
    key2: object,
    letterbox1: Rect,
    letterbox2: Rect,
    *,
    side1: Sequence[PlanTile],
    side2: Sequence[PlanTile],
    diff_key: object | None = None,
    diff_tiles: Sequence[PlanTile] = (),
    layer_px: float,
    sliver_min: float = SLIVER_MIN,
    bbox_eps: float = BBOX_EPS,
) -> list[ComparePairPlan]:
    """Fixed-pair cross-product draw plan: every (side1 tile, side2 tile)
    combination whose on-screen (letterbox-mapped) rects actually overlap,
    resolved to array slots/content scales.

    ``side1``/``side2``/``diff_tiles`` are pre-enumerated visible tiles; the
    caller hands in the actually-resident subset (never a raw geometry
    target list) and this function additionally skips any entry with no
    array slot yet, so the returned plan can never contain a non-resident
    item. Pairs whose rects do not overlap in shared screen space are
    filtered here instead of submitting draw instances the fragment shader
    could only ever discard. Pairs whose two sides landed in different
    array textures are skipped (only possible past array capacity; retried
    next frame once eviction/upload catches up).

    Diff (e.g. the SSIM map, generated at side1's resolution and aligned
    with it, sharing ``letterbox1``) resolves to its own multi-tile set
    when its grid is multi-tile -- one split instance per covering diff
    tile, with ``rect_diff`` kept in raw image-fraction space (the space the
    shader subtracts from ``sampleUV``) while ``bbox`` stays common-space.
    A single-tile (or not-yet-registered) diff keeps the one-lookup
    best-overlap behavior; a multi-tile diff with nothing currently visible
    draws the base images with a blank diff rather than reusing the
    single-tile lookup against a grid it was never valid for.
    """
    side2_common = [
        (tile, to_common_space(tile.rect, letterbox2)) for tile in side2
    ]
    diff_grid = tile_service.grid_for(diff_key) if diff_key is not None else None
    diff_is_multi_tile = diff_grid is not None and not (
        diff_grid.rows == 1 and diff_grid.columns == 1
    )
    diff_common: list[tuple[PlanTile, Rect]] = []
    if diff_is_multi_tile:
        diff_common = [
            (tile, to_common_space(tile.rect, letterbox1)) for tile in diff_tiles
        ]
    items: list[ComparePairPlan] = []
    for tile1 in side1:
        slot1 = tile_service.slot_for(key1, tile1.index)
        if slot1 is None:
            continue
        array_index1, layer1 = slot1
        scale1 = content_scale_for(
            tile_service.content_size_for(key1, tile1.index), layer_px
        )
        fallback_diff_layer, fallback_diff_scale = 0, (1.0, 1.0)
        if diff_key is not None and not diff_is_multi_tile:
            diff_src, diff_idx = _resolve_single_diff_index(
                tile_service, diff_key, tile1.rect
            )
            diff_slot = tile_service.slot_for(diff_src, diff_idx)
            if diff_slot is not None and diff_slot[0] == array_index1:
                fallback_diff_layer = diff_slot[1]
                fallback_diff_scale = content_scale_for(
                    tile_service.content_size_for(diff_src, diff_idx), layer_px
                )
        common1 = to_common_space(tile1.rect, letterbox1)
        for tile2, common2 in side2_common:
            if not rects_overlap(common1, common2):
                continue
            slot2 = tile_service.slot_for(key2, tile2.index)
            if slot2 is None:
                continue
            array_index2, layer2 = slot2
            if array_index2 != array_index1:
                continue
            scale2 = content_scale_for(
                tile_service.content_size_for(key2, tile2.index), layer_px
            )
            pair_bbox = intersection_rect(common1, common2)
            # Filter floating-point seam slivers (see SLIVER_MIN).
            if pair_bbox[2] < sliver_min or pair_bbox[3] < sliver_min:
                continue
            pair_bbox = _expand_bbox(pair_bbox, bbox_eps)
            content_scale = (*scale1, *scale2)
            if not diff_is_multi_tile:
                items.append(
                    ComparePairPlan(
                        rect1=tile1.rect,
                        rect2=tile2.rect,
                        index1=tile1.index,
                        index2=tile2.index,
                        bbox=pair_bbox,
                        content_scale=content_scale,
                        content_scale_diff=fallback_diff_scale,
                        layer1=layer1,
                        layer2=layer2,
                        layer_diff=fallback_diff_layer,
                        array_index=array_index1,
                    )
                )
                continue
            emitted_for_pair = False
            for diff_tile, diff_common_rect in diff_common:
                if not rects_overlap(pair_bbox, diff_common_rect):
                    continue
                diff_slot = tile_service.slot_for(diff_key, diff_tile.index)
                if diff_slot is None or diff_slot[0] != array_index1:
                    continue
                diff_bbox = intersection_rect(pair_bbox, diff_common_rect)
                if diff_bbox[2] < sliver_min or diff_bbox[3] < sliver_min:
                    continue
                diff_bbox = _expand_bbox(diff_bbox, bbox_eps)
                emitted_for_pair = True
                items.append(
                    ComparePairPlan(
                        rect1=tile1.rect,
                        rect2=tile2.rect,
                        index1=tile1.index,
                        index2=tile2.index,
                        bbox=diff_bbox,
                        rect_diff=diff_tile.rect,
                        content_scale=content_scale,
                        content_scale_diff=content_scale_for(
                            tile_service.content_size_for(
                                diff_key, diff_tile.index
                            ),
                            layer_px,
                        ),
                        layer1=layer1,
                        layer2=layer2,
                        layer_diff=diff_slot[1],
                        array_index=array_index1,
                    )
                )
            if not emitted_for_pair:
                # No resident diff tile covers this pair's footprint yet
                # (still uploading) -- draw the base images anyway rather
                # than lose them for this frame; diff shows blank there
                # until its tile arrives.
                items.append(
                    ComparePairPlan(
                        rect1=tile1.rect,
                        rect2=tile2.rect,
                        index1=tile1.index,
                        index2=tile2.index,
                        bbox=pair_bbox,
                        content_scale=content_scale,
                        content_scale_diff=(1.0, 1.0),
                        layer1=layer1,
                        layer2=layer2,
                        layer_diff=0,
                        array_index=array_index1,
                    )
                )
    return items
