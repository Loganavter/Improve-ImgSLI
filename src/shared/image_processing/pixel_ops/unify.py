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
    should_abort=None,
) -> tuple[TiledPixelStore | Image.Image | None, TiledPixelStore | Image.Image | None]:
    """Unify two sources to a common canvas (max width/height per side).

    ``should_abort`` is polled between output strips; a superseded unify
    (newer pair scheduled) must stop burning CPU/IO instead of finishing a
    result nobody will use. On abort partial stores are closed and
    ``(None, None)`` is returned.
    """
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
        if hasattr(source, "width") and hasattr(source, "height"):
            w = source.width() if callable(source.width) else source.width
            h = source.height() if callable(source.height) else source.height
            return (int(w), int(h))
        if hasattr(source, "size"):
            s = source.size() if callable(source.size) else source.size
            if hasattr(s, "width") and hasattr(s, "height"):
                return (int(s.width()), int(s.height()))
            if isinstance(s, (tuple, list)):
                return (int(s[0]), int(s[1]))
        return (0, 0)

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

    if (w1, h1) == (target_w, target_h) and (w2, h2) == (target_w, target_h):
        return source1, source2

    out1 = source1 if (w1, h1) == (target_w, target_h) else None
    out2 = source2 if (w2, h2) == (target_w, target_h) else None

    if out1 is None and source1 is not None:
        try:
            out1 = TiledPixelStore.allocate(target_w, target_h)
            if not write_resampled_to_store(
                out1, source1, target_w, target_h, resample, should_abort=should_abort
            ):
                out1.close()
                return None, None
        except OSError as exc:
            logger.warning("Tile-native unify memmap failed for source1, falling back to PIL: %s", exc)
            from shared.image_processing.resize import resize_images_processor
            pil1 = to_real_pil_copy(source1)
            pil2 = to_real_pil_copy(source2) if source2 is not None else None
            u1, u2 = resize_images_processor(pil1, pil2, method_name)
            return maybe_wrap_pixel_store(u1), maybe_wrap_pixel_store(u2)

    if out2 is None and source2 is not None:
        try:
            out2 = TiledPixelStore.allocate(target_w, target_h)
            if not write_resampled_to_store(
                out2, source2, target_w, target_h, resample, should_abort=should_abort
            ):
                out2.close()
                if out1 is not source1:
                    out1.close()
                return None, None
        except OSError as exc:
            logger.warning("Tile-native unify memmap failed for source2, falling back to PIL: %s", exc)
            from shared.image_processing.resize import resize_images_processor
            pil1 = to_real_pil_copy(source1) if source1 is not None else None
            pil2 = to_real_pil_copy(source2) if source2 is not None else None
            u1, u2 = resize_images_processor(pil1, pil2, method_name)
            return maybe_wrap_pixel_store(u1), maybe_wrap_pixel_store(u2)

    return out1, out2
