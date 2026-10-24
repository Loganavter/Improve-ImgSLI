import logging
from typing import Optional, Tuple

import numpy as np
from PIL import Image

from shared.analysis.differ import _resolve_ssim_win_size, resample_second_to_first
from shared.analysis.output import to_u8_rgb

logger = logging.getLogger("ImproveImgSLI")

# skimage.metrics drags numpy + scipy.stats + skimage on first import (measured
# 2026-10-24 on the frozen D3D11 build: 2408 ms + 3462 ms of GUI-thread stalls,
# inside plugin discovery, because the import sat at module scope). Keep it
# lazy: the scalar metrics are computed rarely, and core/import_warmup pre-loads
# the modules on a daemon thread so the first real use is instant.
def _skimage_metrics():
    from skimage.metrics import (
        peak_signal_noise_ratio as _psnr,
        structural_similarity as _ssim,
    )

    return _psnr, _ssim


def _pair_arrays(image1: Image.Image, image2: Image.Image):
    """Shared input prep for scalars: guards, ONE size-mismatch policy,
    16-bit scaling. Returns ``(arr1, arr2)`` or None (refuse)."""
    if not image1 or not image2:
        return None
    try:
        if image1.size != image2.size:
            # Same resample-and-record policy as the map paths
            # (differ.resample_second_to_first): the scalar is computed
            # over the same resampled pixels the map shows.
            image1, image2, _ = resample_second_to_first(image1, image2)
            if image1.size != image2.size:
                return None
        arr1 = np.asarray(to_u8_rgb(image1))
        arr2 = np.asarray(to_u8_rgb(image2))
    except Exception:
        return None
    if arr1.shape != arr2.shape:
        return None
    return arr1, arr2


def calculate_psnr(image1: Image.Image, image2: Image.Image) -> Optional[float]:
    pair = _pair_arrays(image1, image2)
    if pair is None:
        return None

    try:
        arr1, arr2 = pair
        return _skimage_metrics()[0](arr1, arr2, data_range=255)
    except Exception as e:
        logger.error(f"Error calculating PSNR: {e}", exc_info=True)
        return None


def calculate_ssim(image1: Image.Image, image2: Image.Image) -> Optional[float]:
    pair = _pair_arrays(image1, image2)
    if pair is None:
        return None

    try:
        arr1, arr2 = pair
        height, width = arr1.shape[:2]
        # Shared win-size clamp with the map path
        # (differ._resolve_ssim_win_size): small images get the same odd
        # window the tiled SSIM uses instead of skimage's default, so the
        # scalar and the map agree on what they measured.
        win_size = _resolve_ssim_win_size(width, height)
        return _skimage_metrics()[1](arr1, arr2, data_range=255, channel_axis=2, win_size=win_size)
    except Exception as e:
        logger.error(f"Error calculating SSIM: {e}", exc_info=True)
        return None


def calculate_metrics(
    image1: Image.Image, image2: Image.Image
) -> Optional[Tuple[float, float]]:
    pair = _pair_arrays(image1, image2)
    if pair is None:
        return None

    try:
        arr1, arr2 = pair
        height, width = arr1.shape[:2]
        win_size = _resolve_ssim_win_size(width, height)

        psnr_val = _skimage_metrics()[0](arr1, arr2, data_range=255)
        ssim_val = _skimage_metrics()[1](arr1, arr2, data_range=255, channel_axis=2, win_size=win_size)

        return psnr_val, ssim_val
    except Exception as e:
        logger.error(f"Error calculating metrics: {e}", exc_info=True)
        return None
