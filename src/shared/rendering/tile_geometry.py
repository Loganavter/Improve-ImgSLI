from __future__ import annotations

# 1px of real neighboring source pixels duplicated on every tile edge so
# bilinear filtering at a tile boundary samples true neighbor data instead
# of ClampToEdge-repeating its own edge texel (which would show as a seam).
# Any canvas that composites multiple GPU tiles into one continuous image
# (the compare tabs, ...) needs this same apron, so it lives here rather
# than under one tab.
_TILE_APRON_PX = 1
# Extra ring of tiles kept GPU-resident beyond what's strictly visible this
# frame, so a one-tile pan/zoom nudge doesn't immediately re-crop/re-upload
# from the CPU-side cached image next frame.
_TILE_RESIDENCY_MARGIN = 1


def _apron_rect(
    total_width: int, total_height: int, region, apron: int = _TILE_APRON_PX
) -> tuple[int, int, int, int]:
    left = max(0, region.left - apron)
    top = max(0, region.top - apron)
    right = min(total_width, region.right + apron)
    bottom = min(total_height, region.bottom + apron)
    return left, top, right, bottom
