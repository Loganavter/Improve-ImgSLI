"""Pure geometry for the per-array-layer mip cascade (docs/dev/rendering/
tile-array-atlas-plan.md Phase 9), shared by every tab that regenerates
tile-array mips via ``generate_all_dirty_mips`` instead of a whole-array
``QRhiResourceUpdateBatch.generateMips`` call. Layer pixel size differs per
tab (each derives its own ``_ARRAY_LAYER_PX`` from its own tile extent +
apron), so every function here takes it as a parameter rather than
hardcoding one tab's constant.
"""

from __future__ import annotations


def mip_level_count(layer_px: int) -> int:
    """Levels 0..N-1 for a square ``layer_px`` texture, down to (and
    including) the 1x1 level -- matches what ``QRhiTexture.Flag.MipMapped``
    auto-sizes for any texture this size, so cascading up to this count
    reproduces a full, GL-completeness-safe chain (QRhiSampler exposes no
    LOD-range clamp to safely leave levels unpopulated instead)."""
    size = layer_px
    count = 1
    while size > 1:
        size //= 2
        count += 1
    return count


def mip_level_pixel_size(layer_px: int, level: int) -> tuple[int, int]:
    """Pixel size of ``level`` in a ``layer_px``-square mip chain -- matches
    the halving ``mip_level_count`` already reproduces for
    ``QRhiTexture.Flag.MipMapped``'s auto-sizing, so this needs no probe
    render target to ask the RHI for the size."""
    size = layer_px
    for _ in range(level):
        size = max(1, size // 2)
    return (size, size)
