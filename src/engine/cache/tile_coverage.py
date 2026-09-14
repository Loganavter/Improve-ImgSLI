"""Screen-space coverage/overlap primitives shared by every tab's fallback-LOD
tile drawing (docs/dev/rendering/tile-array-atlas-plan.md Phase 9-11): while a
new LOD/pyramid level's tiles are still uploading, a renderer draws the
previous level's still-resident tiles underneath so the screen doesn't show a
blank hole, then needs to know which of those fallback tiles are already
fully replaced by the current level's (possibly partial) tiles so they can be
dropped instead of drawn on every frame of the transition.
"""

from __future__ import annotations

# A fallback-LOD tile's grid doesn't align with the current level's (they're
# different pyramid levels, so different row/column counts) -- one coarse
# old tile's footprint typically spans several fine new tiles. Requiring
# near-total (not just any) area coverage before dropping it means a fallback
# tile survives until *all* the new tiles over its footprint are actually
# ready, not just the first one to arrive.
FALLBACK_COVERAGE_THRESHOLD = 0.98

# docs/dev/rendering/tile-array-atlas-plan.md Phase 11: point-sampling grid
# resolution for covered_fraction. 9x9=81 points per call is cheap (this
# runs during CPU draw-plan building, not the GPU hot path) and plenty
# precise for a threshold check at FALLBACK_COVERAGE_THRESHOLD's
# granularity -- this is a coverage *estimate*, same tolerance the 0.98
# threshold above already assumes.
COVERAGE_SAMPLE_GRID = 9


def to_common_space(
    rect: tuple[float, float, float, float],
    letterbox: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """Maps a tile's own-image-fraction ``rect`` into a shared on-screen
    space via ``(lx + rx*lw, ly + ry*lh, rw*lw, rh*lh)`` -- the same
    transform a comparison fragment shader applies (``sampleUV = (uv -
    letterbox.xy) / letterbox.zw``, inverted) before checking whether a
    pixel falls inside a tile. Callers with no letterbox concept (a single
    full-canvas slot, not a split comparison) pass the identity letterbox
    ``(0.0, 0.0, 1.0, 1.0)``, making this a no-op passthrough."""
    rx, ry, rw, rh = rect
    lx, ly, lw, lh = letterbox
    return (lx + rx * lw, ly + ry * lh, rw * lw, rh * lh)


def rects_overlap(
    rect_a: tuple[float, float, float, float],
    rect_b: tuple[float, float, float, float],
) -> bool:
    ax, ay, aw, ah = rect_a
    bx, by, bw, bh = rect_b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def intersection_rect(
    rect_a: tuple[float, float, float, float],
    rect_b: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """The overlap rect itself, rather than just its area. Only meaningful
    where ``rects_overlap`` already confirmed a non-empty intersection."""
    ax, ay, aw, ah = rect_a
    bx, by, bw, bh = rect_b
    left = max(ax, bx)
    top = max(ay, by)
    right = min(ax + aw, bx + bw)
    bottom = min(ay + ah, by + bh)
    return (left, top, right - left, bottom - top)


def covered_fraction(
    rect: tuple[float, float, float, float],
    others: list[tuple[float, float, float, float]],
    *,
    samples: int = COVERAGE_SAMPLE_GRID,
) -> float:
    """Fraction of ``rect`` covered by the union of ``others``, estimated by
    point-sampling a ``samples`` x ``samples`` grid across ``rect`` and
    testing point-in-any-``other`` membership.

    Deliberately NOT a sum of per-``other`` intersection areas: ``others``
    routinely contains overlapping/duplicate-covering rects by design here --
    e.g. one side's tile legitimately paired with several tiles on another
    side via apron overlap produces several draw items sharing the same
    rect, and a fallback-dropping caller intentionally draws a fallback tile
    underneath an overlapping current tile during a transition. A naive area
    sum over such a list double- (or N-times-) counts that overlap, which can
    push the summed "covered" area past the rect's own total area even while
    a *different*, genuinely-uncovered region contributes nothing -- silently
    reporting full coverage despite a real hole. This was found live in a
    compare tab: a user-captured log showed `TIME_DEADLINE ...
    uploaded=11/25` (only 11 of 25 needed tiles resident) immediately
    followed by a gap-detection check never firing for the rest of that
    ~8000-line capture, even though the user visually confirmed a hole was
    on screen at that same moment -- one tile's rect appearing in ~7
    duplicate array items (11 resident tiles produced 76 total pairs against
    the other, fully-resident side) was enough to inflate the area-sum well
    past 100% covered for the already-uploaded region, masking the still-
    missing 14 tiles' hole in the aggregate. Point sampling can't be fooled
    this way: each point is either inside at least one ``other`` or it
    isn't, counted once."""
    area = rect[2] * rect[3]
    if area <= 0.0:
        return 1.0
    rx, ry, rw, rh = rect
    if samples <= 1:
        points = [(rx + rw / 2.0, ry + rh / 2.0)]
    else:
        points = [
            (rx + rw * (i + 0.5) / samples, ry + rh * (j + 0.5) / samples)
            for i in range(samples)
            for j in range(samples)
        ]
    covered = 0
    for px, py in points:
        for ox, oy, ow, oh in others:
            if ox <= px <= ox + ow and oy <= py <= oy + oh:
                covered += 1
                break
    return covered / len(points)
