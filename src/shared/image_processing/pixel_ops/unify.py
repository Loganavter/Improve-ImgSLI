"""Tile-native unify: resize both sides to a common canvas into ``TiledPixelStore``."""

from __future__ import annotations

import logging

from PIL import Image

from shared.image_processing.pixel_ops.resample import write_resampled_to_store
from shared.image_processing.tiled_pixel_store import (
    TiledPixelStore,
    maybe_wrap_pixel_store,
    to_real_pil_copy,
)
from shared.image_processing.store_lease import StoreLease

logger = logging.getLogger("ImproveImgSLI")

_RESAMPLE = {
    "NEAREST": Image.Resampling.NEAREST,
    "BILINEAR": Image.Resampling.BILINEAR,
    "BICUBIC": Image.Resampling.BICUBIC,
    "LANCZOS": Image.Resampling.LANCZOS,
}

# Below this size unified output uses PIL resize_images_processor (exact match).
_ACCURATE_UNIFY_MAX_PIXELS = 4096 * 4096


def unify_pair(
    source1,
    source2,
    method_name: str = "LANCZOS",
    *,
    lease1: StoreLease | None = None,
    lease2: StoreLease | None = None,
) -> tuple[TiledPixelStore | Image.Image | None, TiledPixelStore | Image.Image | None]:
    """Unify two sources to a common canvas (max width/height per side)."""
    if lease1 is not None and not lease1.valid:
        return None, None
    if lease2 is not None and not lease2.valid:
        return None, None

    if source1 is None and source2 is None:
        return None, None

    resample = _RESAMPLE.get(method_name.upper(), Image.Resampling.LANCZOS)

    def _size(source):
        if source is None:
            return (0, 0)
        return source.size

    w1, h1 = _size(source1)
    w2, h2 = _size(source2)
    target_w = max(w1, w2)
    target_h = max(h1, h2)
    if target_w <= 0 or target_h <= 0:
        return None, None

    if target_w * target_h <= _ACCURATE_UNIFY_MAX_PIXELS:
        from shared.image_processing.pixel_ops.downscale import downscale_source_to_pil
        from shared.image_processing.resize import resize_images_processor

        pil1 = (
            downscale_source_to_pil(source1, (w1, h1), resample=resample)
            if source1 is not None
            else None
        )
        pil2 = (
            downscale_source_to_pil(source2, (w2, h2), resample=resample)
            if source2 is not None
            else None
        )
        u1, u2 = resize_images_processor(pil1, pil2, method_name)
        return maybe_wrap_pixel_store(u1), maybe_wrap_pixel_store(u2)

    try:
        out1 = TiledPixelStore.allocate(target_w, target_h)
        out2 = TiledPixelStore.allocate(target_w, target_h)
    except OSError as exc:
        logger.warning("Tile-native unify memmap failed, falling back to PIL: %s", exc)
        from shared.image_processing.resize import resize_images_processor

        pil1 = to_real_pil_copy(source1) if source1 is not None else None
        pil2 = to_real_pil_copy(source2) if source2 is not None else None
        u1, u2 = resize_images_processor(pil1, pil2, method_name)
        return maybe_wrap_pixel_store(u1), maybe_wrap_pixel_store(u2)

    if source1 is not None:
        write_resampled_to_store(out1, source1, target_w, target_h, resample)
    if source2 is not None:
        write_resampled_to_store(out2, source2, target_w, target_h, resample)

    return out1, out2
