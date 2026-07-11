"""Pure geometry helpers for magnifier multi-tile capture.

docs/dev/TILED_RENDERING_DESIGN.md Phase 4: when a source image is large
enough to be GPU-tile-resident (see ``RhiCanvasRenderer``/``TileTextureService``),
the magnifier's capture circle can straddle more than one tile. These
functions turn a capture-space ``uv_rect`` (0..1 fraction of the *full*
source image, ``(left, top, right, bottom)`` — matching ``mag.frag``'s
``uvRect1``/``uvRect2`` convention) into a list of per-tile draw slices.

Kept free of Qt/QRhi so it can be unit tested without a GPU: callers pass in
plain data (grid geometry, a ``tile_key`` function, a ``visible_tiles``
callback) rather than live renderer objects.
"""

from __future__ import annotations


def uv_segment_to_tc_range(uv_lo, uv_hi, seg_lo, seg_hi):
    """The tc in [0, 1] (relative to ``uv_lo..uv_hi``) covered by ``seg_lo..seg_hi``.

    ``tc=0`` is ``uv_lo``, ``tc=1`` is ``uv_hi`` (matches ``mix(uvRect.xy, uvRect.zw, tc)``
    in the shader). Returns ``None`` if the segment doesn't overlap the uv range.
    """
    span = uv_hi - uv_lo
    if abs(span) <= 1e-12:
        return (0.0, 1.0)
    tc0 = (seg_lo - uv_lo) / span
    tc1 = (seg_hi - uv_lo) / span
    lo, hi = (tc0, tc1) if tc0 <= tc1 else (tc1, tc0)
    lo = max(0.0, lo)
    hi = min(1.0, hi)
    if lo >= hi:
        return None
    return (lo, hi)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def remap_slice_uv_to_tc(slice_: dict, tc_x: tuple, tc_y: tuple) -> tuple:
    """Re-parameterize a slice's tile-local uv_rect to a narrower tc sub-range.

    ``slice_["uv_rect"]`` is affine in tc over ``slice_["tc_x"]``/``["tc_y"]``
    (by construction of ``tile_uv_slices``), so a narrower ``tc_x``/``tc_y``
    (a subset of the slice's own range) maps to a narrower uv_rect via linear
    interpolation — no need to re-derive tile geometry.
    """
    left, top, right, bottom = slice_["uv_rect"]
    stx0, stx1 = slice_["tc_x"]
    sty0, sty1 = slice_["tc_y"]
    fx0 = (tc_x[0] - stx0) / (stx1 - stx0) if stx1 != stx0 else 0.0
    fx1 = (tc_x[1] - stx0) / (stx1 - stx0) if stx1 != stx0 else 1.0
    fy0 = (tc_y[0] - sty0) / (sty1 - sty0) if sty1 != sty0 else 0.0
    fy1 = (tc_y[1] - sty0) / (sty1 - sty0) if sty1 != sty0 else 1.0
    return (
        _lerp(left, right, fx0),
        _lerp(top, bottom, fy0),
        _lerp(left, right, fx1),
        _lerp(top, bottom, fy1),
    )


def restrict_tc_axis(tc_x: tuple, tc_y: tuple, axis: str, lo: float, hi: float):
    """Intersect one axis of a tc rect with ``[lo, hi]`` (combined-mode half-split)."""
    if axis == "x":
        new_lo, new_hi = max(tc_x[0], lo), min(tc_x[1], hi)
        if new_lo >= new_hi:
            return None
        return (new_lo, new_hi), tc_y
    new_lo, new_hi = max(tc_y[0], lo), min(tc_y[1], hi)
    if new_lo >= new_hi:
        return None
    return tc_x, (new_lo, new_hi)


def intersect_tc_rects(a_x: tuple, a_y: tuple, b_x: tuple, b_y: tuple):
    lo_x, hi_x = max(a_x[0], b_x[0]), min(a_x[1], b_x[1])
    lo_y, hi_y = max(a_y[0], b_y[0]), min(a_y[1], b_y[1])
    if lo_x >= hi_x or lo_y >= hi_y:
        return None
    return (lo_x, hi_x), (lo_y, hi_y)


def tile_uv_slices(
    grid,
    tile_key_fn,
    source_key,
    uv_rect: tuple,
    *,
    apron_px: int,
    apron_rect_fn,
    visible_tiles_fn,
) -> list:
    """Slice ``uv_rect`` (full-image 0..1 fraction) against a source's tile grid.

    Returns a list of ``{"tile_key", "uv_rect" (tile-local 0..1), "tc_x", "tc_y"}``.
    A ``None``/1x1 grid (source not tiled) yields a single passthrough slice
    covering the whole ``uv_rect`` unchanged, so callers don't need a separate
    non-tiled code path.
    """
    if grid is None or (grid.rows == 1 and grid.columns == 1):
        return [
            {
                "tile_key": source_key,
                "uv_rect": tuple(uv_rect),
                "tc_x": (0.0, 1.0),
                "tc_y": (0.0, 1.0),
            }
        ]

    left, top, right, bottom = uv_rect
    total_w, total_h = float(grid.total_width), float(grid.total_height)
    rect_x_lo = min(left, right) * total_w
    rect_x_hi = max(left, right) * total_w
    rect_y_lo = min(top, bottom) * total_h
    rect_y_hi = max(top, bottom) * total_h
    indices = visible_tiles_fn((rect_x_lo, rect_y_lo, rect_x_hi, rect_y_hi))
    regions = {(row, col): region for row, col, region in grid.iter_regions()}

    slices = []
    for row, col in indices:
        region = regions.get((row, col))
        if region is None:
            continue
        tile_left, tile_top, tile_right, tile_bottom = apron_rect_fn(
            grid.total_width, grid.total_height, region, apron_px
        )
        tcx = uv_segment_to_tc_range(left, right, tile_left / total_w, tile_right / total_w)
        tcy = uv_segment_to_tc_range(top, bottom, tile_top / total_h, tile_bottom / total_h)
        if tcx is None or tcy is None:
            continue
        sub_left = left + tcx[0] * (right - left)
        sub_right = left + tcx[1] * (right - left)
        sub_top = top + tcy[0] * (bottom - top)
        sub_bottom = top + tcy[1] * (bottom - top)
        tile_w_px = tile_right - tile_left
        tile_h_px = tile_bottom - tile_top
        if tile_w_px <= 0 or tile_h_px <= 0:
            continue
        local_l = (sub_left * total_w - tile_left) / tile_w_px
        local_r = (sub_right * total_w - tile_left) / tile_w_px
        local_t = (sub_top * total_h - tile_top) / tile_h_px
        local_b = (sub_bottom * total_h - tile_top) / tile_h_px
        slices.append(
            {
                "tile_key": tile_key_fn(source_key, row, col),
                "uv_rect": (local_l, local_t, local_r, local_b),
                "tc_x": tcx,
                "tc_y": tcy,
            }
        )
    return slices


def dual_source_tile_pairs(slices1: list, slices2: list) -> list:
    """Cross-join two sources' tile slices for simultaneous-sampling draws.

    Used by diff-computation modes (``mag.frag``'s ``computeDiff``) that read
    ``bgTex1``/``bgTex2`` at the same ``tc`` in one draw call: each output
    pair's tc rect is the intersection of both slices' own tc ranges, since
    that's the region where *both* chosen tile textures are simultaneously
    the correct ones to sample.
    """
    pairs = []
    for s1 in slices1:
        for s2 in slices2:
            tc = intersect_tc_rects(s1["tc_x"], s1["tc_y"], s2["tc_x"], s2["tc_y"])
            if tc is None:
                continue
            tc_x, tc_y = tc
            pairs.append(
                {
                    "tile_key1": s1["tile_key"],
                    "tile_key2": s2["tile_key"],
                    "uv_rect1": remap_slice_uv_to_tc(s1, tc_x, tc_y),
                    "uv_rect2": remap_slice_uv_to_tc(s2, tc_x, tc_y),
                    "tc_x": tc_x,
                    "tc_y": tc_y,
                }
            )
    return pairs


def tc_rect_to_widget_px(
    cx_px: float, cy_px: float, content_radius: float, tc_x: tuple, tc_y: tuple
) -> tuple:
    """Map a tc sub-rect to a widget-px screen rect for scissor clipping.

    Mirrors ``mag.vert``'s vertex mapping: ``x`` is a direct affine map of
    ``tc.x``, but ``y`` is inverted (``y = mix(quadBounds.y, quadBounds.w, 1 - tc.y)``),
    so increasing ``tc.y`` moves toward the screen top.
    """
    x0 = cx_px - content_radius + tc_x[0] * (2.0 * content_radius)
    x1 = cx_px - content_radius + tc_x[1] * (2.0 * content_radius)
    y_at_tc0 = cy_px + content_radius - tc_y[0] * (2.0 * content_radius)
    y_at_tc1 = cy_px + content_radius - tc_y[1] * (2.0 * content_radius)
    y0, y1 = (y_at_tc0, y_at_tc1) if y_at_tc0 <= y_at_tc1 else (y_at_tc1, y_at_tc0)
    return x0, y0, max(0.0, x1 - x0), max(0.0, y1 - y0)


def intersect_widget_rects(a: tuple, b: tuple) -> tuple:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    left = max(ax, bx)
    top = max(ay, by)
    right = min(ax + aw, bx + bw)
    bottom = min(ay + ah, by + bh)
    return left, top, max(0.0, right - left), max(0.0, bottom - top)


_FULL_TC = ((0.0, 1.0), (0.0, 1.0))


def is_full_tc(tc_x: tuple, tc_y: tuple) -> bool:
    return tc_x == _FULL_TC[0] and tc_y == _FULL_TC[1]


def build_tile_records(
    *,
    source_slices_fn,
    combined: bool,
    source_mode: int,
    diff_mode: int,
    uv_rect1: tuple,
    uv_rect2: tuple,
    tex_key_1,
    tex_key_2,
    diff_key,
    internal_split: float,
    comb_horizontal: bool,
) -> list:
    """Per-quad draw records for ``MagnifierPass``.

    ``source_slices_fn(source_key, uv_rect) -> list[slice]`` is the only
    renderer-dependent hook (calls into ``TileTextureService``); everything
    else here is pure. Each returned record has ``tc_x``, ``tc_y``,
    ``uv_rect1``, ``uv_rect2``, and one of ``tex1_key``/``tex2_key``/``texd_key``
    set to the tile to bind (others ``None`` — unused by the shader for that
    record's sampling branch, left as the caller's placeholder).
    """
    if combined:
        axis = "y" if comb_horizontal else "x"
        records = []
        for half_is_source0, uv_rect, tex_key, split_lo, split_hi in (
            (True, uv_rect1, tex_key_1, 0.0, internal_split),
            (False, uv_rect2, tex_key_2, internal_split, 1.0),
        ):
            for sl in source_slices_fn(tex_key, uv_rect):
                restricted = restrict_tc_axis(sl["tc_x"], sl["tc_y"], axis, split_lo, split_hi)
                if restricted is None:
                    continue
                tc_x, tc_y = restricted
                uv = remap_slice_uv_to_tc(sl, tc_x, tc_y)
                rec = {
                    "tc_x": tc_x,
                    "tc_y": tc_y,
                    "uv_rect1": uv if half_is_source0 else uv_rect1,
                    "uv_rect2": uv_rect2 if half_is_source0 else uv,
                    "tex1_key": sl["tile_key"] if half_is_source0 else None,
                    "tex2_key": None if half_is_source0 else sl["tile_key"],
                    "texd_key": None,
                }
                records.append(rec)
        return records

    if source_mode == 2 and diff_mode in (1, 2):
        slices1 = source_slices_fn(tex_key_1, uv_rect1)
        slices2 = source_slices_fn(tex_key_2, uv_rect2)
        return [
            {
                "tc_x": pair["tc_x"],
                "tc_y": pair["tc_y"],
                "uv_rect1": pair["uv_rect1"],
                "uv_rect2": pair["uv_rect2"],
                "tex1_key": pair["tile_key1"],
                "tex2_key": pair["tile_key2"],
                "texd_key": None,
            }
            for pair in dual_source_tile_pairs(slices1, slices2)
        ]

    if source_mode == 2:
        active_key = tex_key_1 if diff_mode == 3 else diff_key
        active_uv = uv_rect1
        slot = "tex1_key" if diff_mode == 3 else "texd_key"
    elif source_mode == 1:
        active_key, active_uv, slot = tex_key_2, uv_rect2, "tex2_key"
    else:
        active_key, active_uv, slot = tex_key_1, uv_rect1, "tex1_key"

    records = []
    for sl in source_slices_fn(active_key, active_uv):
        rec = {
            "tc_x": sl["tc_x"],
            "tc_y": sl["tc_y"],
            "uv_rect1": uv_rect1,
            "uv_rect2": uv_rect2,
            "tex1_key": None,
            "tex2_key": None,
            "texd_key": None,
        }
        if slot in ("tex1_key", "texd_key"):
            rec["uv_rect1"] = sl["uv_rect"]
        else:
            rec["uv_rect2"] = sl["uv_rect"]
        rec[slot] = sl["tile_key"]
        records.append(rec)
    return records
