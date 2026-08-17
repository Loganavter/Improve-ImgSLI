"""Shared region resampling for unify/downscale tile writers."""

from __future__ import annotations

from PIL import Image

from shared.image_processing.tiled_pixel_store import TiledPixelStore, pixel_source_size

_BLOCK = 512


def crop_source(source, box: tuple[int, int, int, int]) -> Image.Image:
    from PySide6.QtGui import QImage
    if isinstance(source, QImage):
        left, top, right, bottom = box
        cropped_qimg = source.copy(left, top, right - left, bottom - top)
        if cropped_qimg.format() != QImage.Format.Format_RGBA8888:
            cropped_qimg = cropped_qimg.convertToFormat(QImage.Format.Format_RGBA8888)
        return Image.frombytes("RGBA", (cropped_qimg.width(), cropped_qimg.height()), bytes(cropped_qimg.constBits()))
        
    if isinstance(source, TiledPixelStore):
        return source.crop(box)
    return source.crop(box)


def resample_output_region(
    source,
    target_w: int,
    target_h: int,
    out_box: tuple[int, int, int, int],
    resample: Image.Resampling,
) -> Image.Image:
    """Map an output pixel rectangle back to source space and resample."""
    ox0, oy0, ox1, oy1 = out_box

    sw, sh = pixel_source_size(source)
    scale_x = sw / float(target_w)
    scale_y = sh / float(target_h)
    sx0 = int(ox0 * scale_x)
    sy0 = int(oy0 * scale_y)
    sx1 = max(sx0 + 1, int(ox1 * scale_x))
    sy1 = max(sy0 + 1, int(oy1 * scale_y))
    ow, oh = ox1 - ox0, oy1 - oy0
    return crop_source(source, (sx0, sy0, sx1, sy1)).resize((ow, oh), resample)


def write_resampled_to_store(
    store: TiledPixelStore,
    source,
    target_w: int,
    target_h: int,
    resample: Image.Resampling,
    *,
    block: int = _BLOCK,
    should_abort=None,
) -> bool:
    """Returns False if aborted mid-write (store contents are partial)."""
    import time
    for oy in range(0, target_h, block):
        if should_abort is not None and should_abort():
            return False
        oy1 = min(oy + block, target_h)
        for ox in range(0, target_w, block):
            ox1 = min(ox + block, target_w)
            box = (ox, oy, ox1, oy1)
            store.write_pil(
                box,
                resample_output_region(source, target_w, target_h, box, resample),
            )
        time.sleep(0.001)
    return True