"""Pyramid level selection shared by live render and snapshot/export paths.

Both paths must call :func:`select_level` with the same inputs so live canvas,
export preview, final export and video snapshots pick identical mipmap levels
(docs/dev/rendering/rendering-model.md parity requirement).
"""

from __future__ import annotations

import math
from typing import NamedTuple


class LevelKey(NamedTuple):
    """Texture key for a non-base pyramid level of ``base`` (level >= 1).

    Level 0 keeps the bare base key so the no-pyramid path stays
    byte-identical; a distinct type (not a plain tuple) keeps these keys
    unambiguous next to ``TileTextureService``'s ``(source_id, row, col)``
    tile keys.

    ``generation`` is the base-store generation the level was sampled from:
    a reunified base reuses the same ``(base, level)`` pair with a fresh
    generation, so the key stays ``(uid, level, generation)`` and stale
    entries never alias live ones. Defaults to ``0`` so existing two-field
    constructions keep working.
    """

    base: object
    level: int
    generation: int = 0


def select_level(dest_scale: float, level_count: int) -> int:
    """Pick the pyramid level to render at ``dest_scale``.

    ``dest_scale`` is on-screen pixels per level-0 source pixel (viewport zoom
    times device pixel ratio). Level ``k`` halves resolution ``k`` times, so a
    level-``k`` texel spans ``dest_scale * 2**k`` screen pixels. The chosen
    level is the coarsest one whose texels still cover at most one screen
    pixel — never coarser than the destination needs, never finer than useful.
    """
    if level_count <= 1:
        return 0
    if dest_scale >= 1.0:
        return 0
    if dest_scale <= 0.0 or not math.isfinite(dest_scale):
        return level_count - 1
    level = int(math.floor(math.log2(1.0 / dest_scale)))
    return max(0, min(level, level_count - 1))


def demand_level(dest_scale: float, level_count: int) -> int:
    """Shared level pick for a view scale. Thin, behaviour-identical wrapper
    over :func:`select_level` (the single place tabs may name a demanded
    level; no tab re-implements the log2 math)."""
    return select_level(dest_scale, level_count)


def dest_scale_fit(
    fb_size: tuple[int, int], source_size: tuple[int, int], zoom: float
) -> float:
    """Display pixels per level-0 source pixel for a fit-to-box view.

    ``min(fb_w / src_w, fb_h / src_h) * zoom`` (the limiting axis). Mirrors
    the long-standing QL/Image-Compare fit formula exactly: non-positive
    source sizes yield ``0.0``, and a non-finite ``zoom`` propagates as the
    old inline ``min(...) * zoom`` did (``select_level`` handles inf/nan
    itself — clamping here would change the picked level). Never raises."""
    try:
        fb_w, fb_h = int(fb_size[0]), int(fb_size[1])
        src_w, src_h = int(source_size[0]), int(source_size[1])
        z = float(zoom)
    except Exception:
        return 0.0
    if src_w <= 0 or src_h <= 0:
        return 0.0
    return min(float(fb_w) / float(src_w), float(fb_h) / float(src_h)) * z
