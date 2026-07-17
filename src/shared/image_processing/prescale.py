"""Pre-scale image pairs to a target output size.

Used by video export and preview rendering to avoid processing
full-resolution images when the output is much smaller.
"""
from __future__ import annotations

from PIL import Image

from shared.image_processing.pixel_ops.resample import write_resampled_to_store
from shared.image_processing.tiled_pixel_store import TiledPixelStore

_RESAMPLE = {
    "NEAREST": Image.Resampling.NEAREST,
    "BILINEAR": Image.Resampling.BILINEAR,
    "BICUBIC": Image.Resampling.BICUBIC,
    "LANCZOS": Image.Resampling.LANCZOS,
    "EWA_LANCZOS": Image.Resampling.LANCZOS,
}


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

    resample = _RESAMPLE.get(str(method_name).upper(), Image.Resampling.LANCZOS)
    tw, th = target_size

    def _resize(source) -> TiledPixelStore:
        store_in = _as_store(source)
        if store_in.size == (tw, th):
            return store_in
        out = TiledPixelStore.allocate(tw, th)
        write_resampled_to_store(out, store_in, tw, th, resample)
        return out

    return _resize(img1), _resize(img2)
