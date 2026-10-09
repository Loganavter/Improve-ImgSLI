"""Phase-aligned tile crop boxes for CPU analysis (no Qt, no GPU lattice).

The 8-px DCT block grid only exists at native resolution, so analysis tiles
must be cropped at origins that are multiples of 8 and must stay small enough
that the detectors' internal 512 downscale never engages. This helper owns
that pure geometry; it lives in ``shared/analysis`` (like ``diff_source`` /
``edge_detector``) so tab modules never reference the tile-grid lattice that
``tests/contracts/test_no_private_grid.py`` seals to ``TileTextureService``.
"""

from __future__ import annotations

from engine.store.regions import build_uniform_tile_grid

#: Default cropped-tile extent upper bound. Must stay <= 512 so the detectors'
#: internal downscale never engages.
DEFAULT_TILE = 512
#: Default apron (must be a multiple of 8 to keep the crop origin in phase).
DEFAULT_OVERLAP = 8


def _snap8(value: int) -> int:
    """Round *value* down to the nearest multiple of 8 (>= 0)."""
    v = int(value)
    if v <= 0:
        return 0
    return (v // 8) * 8


def _effective_geometry(tile: int, overlap: int) -> tuple[int, int, int]:
    """Normalize (tile, overlap) into (tile, overlap, core).

    ``core`` is the grid's max tile extent — the part that must be covered by
    every region — and ``core + 2 * overlap`` never exceeds ``tile``.
    """
    tile = max(8, int(tile))
    overlap = max(0, int(overlap))
    overlap = min(overlap, max(0, (tile - 8) // 2))
    overlap = _snap8(overlap)
    core = max(8, _snap8(tile - 2 * overlap))
    return tile, overlap, core


def tile_crop_boxes(
    width: int,
    height: int,
    *,
    tile: int = DEFAULT_TILE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[tuple[int, int, int, int]]:
    """Phase-aligned crop boxes covering a ``width`` x ``height`` source.

    Boxes are ``(left, top, right, bottom)``. Every origin is a multiple of 8
    (the block grid phase) and every extent is <= ``tile`` so the detectors'
    own downscale never engages. The union of the boxes covers the whole
    source; the apron (``overlap``) extends each core region outward so
    tile-border edge effects do not leak into the aggregate.
    """
    width = max(1, int(width))
    height = max(1, int(height))
    tile, overlap, core = _effective_geometry(tile, overlap)
    grid = build_uniform_tile_grid(
        width,
        height,
        max_tile_width=core,
        max_tile_height=core,
    )
    boxes: list[tuple[int, int, int, int]] = []
    for _row, _col, region in grid.iter_regions():
        core_left = _snap8(region.left)
        core_top = _snap8(region.top)
        left = max(0, core_left - overlap)
        top = max(0, core_top - overlap)
        right = min(width, region.right + overlap, left + tile)
        bottom = min(height, region.bottom + overlap, top + tile)
        if right > left and bottom > top:
            boxes.append((left, top, right, bottom))
    return boxes
