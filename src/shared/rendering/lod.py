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
    """

    base: object
    level: int


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
