"""Pre-scale image pairs to a target output size.

Used by video export and preview rendering to avoid processing
full-resolution images when the output is much smaller.
"""
from __future__ import annotations

from PIL import Image

import logging

from shared.image_processing.pixel_ops.resample import write_resampled_to_store
from shared.image_processing.resample_map import get_resample
from shared.image_processing.tiled_pixel_store import TiledPixelStore

logger = logging.getLogger("ImproveImgSLI")


def _as_store(source) -> TiledPixelStore:
    if isinstance(source, TiledPixelStore):
        return source
    if isinstance(source, Image.Image):
        rgba = source if source.mode == "RGBA" else source.convert("RGBA")
        return TiledPixelStore.from_pil(rgba)
    raise TypeError(f"Unsupported prescale source type: {type(source)!r}")


def prescale_pair(
    img1,
    img2,
    output_width: int,
    output_height: int,
    method_name: str = "LANCZOS",
    *,
    should_abort=None,
) -> tuple:
    """Scale *img1* and *img2* to one shared size within the output bounds.

    Accepts ``PIL.Image`` or ``TiledPixelStore``; always returns a pair of
    ``TiledPixelStore`` (display-bounded full-res tier) via tile-native
    resample — no letterbox PIL canvas.

    Export/render paths need the pair unified before the canvas plan is built.
    If a high-res/low-res pair is scaled by one shared ratio first, the low-res
    image can become tiny and then get upscaled again by the unification step.
    Instead, compute the output size from the largest source dimensions and
    resize both images directly to that final shared size.
    """
    if img1 is None or img2 is None:
        return img1, img2

    src_w = max(img1.width, img2.width)
    src_h = max(img1.height, img2.height)

    ratio = min(output_width / src_w, output_height / src_h)
    if ratio >= 1.0:
        target_size = (src_w, src_h)
    else:
        target_size = (
            max(1, int(src_w * ratio)),
            max(1, int(src_h * ratio)),
        )

    resample = get_resample(method_name)
    tw, th = target_size

    def _resize(source) -> TiledPixelStore:
        store_in = _as_store(source)
        if store_in.size == (tw, th):
            return store_in
        try:
            out = TiledPixelStore.allocate(tw, th)
        except OSError as exc:
            logger.warning("prescale memmap failed for %sx%s, returning original source: %s", tw, th, exc)
            return store_in
        try:
            ok = write_resampled_to_store(out, store_in, tw, th, resample, should_abort=should_abort)
        except OSError as exc:
            logger.warning("prescale write failed, falling back to original source: %s", exc)
            try:
                out.close()
            except Exception:
                pass
            return store_in
        if not ok:
            # Aborted (cancelled export) — don't burn CPU to completion.
            try:
                out.close()
            except Exception:
                pass
            return store_in
        return out

    return _resize(img1), _resize(img2)