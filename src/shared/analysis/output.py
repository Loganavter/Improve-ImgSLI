"""The single analysis-output boundary: numpy result -> PIL | TiledPixelStore.

Every analysis entry point (`differ`, `ssim_source`, `edge_detector`,
`channel_analyzer`, `diff_source`) finalizes its numpy result through
:func:`finalize_diff_output` instead of hand-rolling ``Image.fromarray``.
That centralizes the "small result stays in-memory, large result spills to
``TiledPixelStore``" decision in exactly one place, and lets the AST contract
test (``tests/contracts/test_analysis_output_boundary.py``) prove that no
analysis module constructs a full-frame PIL container directly.
"""

from __future__ import annotations

import logging

import numpy as np
from PIL import Image

from shared.image_processing.tiled_pixel_store import TiledPixelStore

logger = logging.getLogger("ImproveImgSLI")

DIFF_SPILL_MAX_DIMENSION = 4096
DIFF_SPILL_MAX_PIXELS = 16_000_000
_BLOCK = 512

_RGBA_MODES = {
    1: "L",
    3: "RGB",
}


def rgba_from_array(arr: np.ndarray) -> Image.Image:
    """Build an RGBA PIL from an (H, W, 4) uint8 array.

    Leaf helper for per-patch channel extraction (``extract_channel``): the
    caller owns a bounded region, so this never spills to a store and always
    returns PIL. Keeps every ``Image.fromarray`` inside this module.
    """
    return Image.fromarray(arr, mode="RGBA")


def finalize_diff_output(
    arr: np.ndarray,
    *,
    channels: int = 1,
) -> Image.Image | TiledPixelStore:
    """Return compact PIL for bounded results, else spill to ``TiledPixelStore``.

    ``channels`` is the numpy array's per-pixel channel count: ``1`` (gray,
    becomes L->RGBA) or ``3`` (RGB->RGBA).
    """
    if channels not in _RGBA_MODES:
        raise ValueError(f"Unsupported output channels: {channels}")
    mode = _RGBA_MODES[channels]
    height, width = arr.shape[:2]
    if (
        width * height <= DIFF_SPILL_MAX_PIXELS
        and max(width, height) <= DIFF_SPILL_MAX_DIMENSION
    ):
        return Image.fromarray(arr, mode=mode).convert("RGBA")

    store = TiledPixelStore.allocate(width, height)
    try:
        for oy in range(0, height, _BLOCK):
            oy1 = min(oy + _BLOCK, height)
            for ox in range(0, width, _BLOCK):
                ox1 = min(ox + _BLOCK, width)
                patch = arr[oy:oy1, ox:ox1]
                pil = Image.fromarray(patch, mode=mode).convert("RGBA")
                store.write_pil((ox, oy, ox1, oy1), pil)
        return store
    except OSError as exc:
        logger.warning("Diff spill to TiledPixelStore failed, keeping PIL: %s", exc)
        return Image.fromarray(arr, mode=mode).convert("RGBA")
