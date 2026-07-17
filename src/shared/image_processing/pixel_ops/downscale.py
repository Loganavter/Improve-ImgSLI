"""Tile-native downscale from ``PixelSource`` to bounded display-tier PIL."""

from __future__ import annotations

from PIL import Image

from shared.image_processing.tiled_pixel_store import TiledPixelStore

_BLOCK = 512


def _crop_source(source, box: tuple[int, int, int, int]) -> Image.Image:
    left, top, right, bottom = box
    if isinstance(source, TiledPixelStore):
        return source.crop((left, top, right, bottom))
    return source.crop((left, top, right, bottom))


def downscale_source_to_pil(
    source,
    target_size: tuple[int, int],
    *,
    resample: Image.Resampling = Image.Resampling.LANCZOS,
) -> Image.Image:
    """Resize ``source`` to ``target_size`` without materializing full-res."""
    if isinstance(source, Image.Image):
        if source.size == target_size:
            rgba = source if source.mode == "RGBA" else source.convert("RGBA")
            return rgba.copy()
        return source.resize(target_size, resample).convert("RGBA")

    if not isinstance(source, TiledPixelStore):
        raise TypeError(f"Unsupported pixel source type: {type(source)!r}")

    target_w, target_h = target_size
    sw, sh = source.size
    if target_w <= 0 or target_h <= 0:
        raise ValueError("target_size must be positive")
    if sw == target_w and sh == target_h:
        return source.crop((0, 0, sw, sh))

    output = Image.new("RGBA", (target_w, target_h))
    scale_x = sw / float(target_w)
    scale_y = sh / float(target_h)

    for oy in range(0, target_h, _BLOCK):
        oh = min(_BLOCK, target_h - oy)
        for ox in range(0, target_w, _BLOCK):
            ow = min(_BLOCK, target_w - ox)
            sx0 = int(ox * scale_x)
            sy0 = int(oy * scale_y)
            sx1 = max(sx0 + 1, int((ox + ow) * scale_x))
            sy1 = max(sy0 + 1, int((oy + oh) * scale_y))
            patch = _crop_source(source, (sx0, sy0, sx1, sy1)).resize(
                (ow, oh), resample
            )
            output.paste(patch.convert("RGBA"), (ox, oy))

    return output


def downscale_pair_to_limit(
    img1,
    img2,
    limit: int,
    *,
    resample: Image.Resampling = Image.Resampling.LANCZOS,
) -> tuple[Image.Image, Image.Image]:
    """Downscale a pair to fit within ``limit`` on the longest edge."""
    w, h = img1.size
    if limit <= 0 or max(w, h) <= limit:
        pil1 = (
            img1
            if isinstance(img1, Image.Image)
            else downscale_source_to_pil(img1, img1.size, resample=resample)
        )
        pil2 = (
            img2
            if isinstance(img2, Image.Image)
            else downscale_source_to_pil(img2, img2.size, resample=resample)
        )
        if pil1.mode != "RGBA":
            pil1 = pil1.convert("RGBA")
        if pil2.mode != "RGBA":
            pil2 = pil2.convert("RGBA")
        return pil1, pil2

    ratio = min(limit / w, limit / h)
    new_w, new_h = max(1, int(w * ratio)), max(1, int(h * ratio))
    target = (new_w, new_h)
    return (
        downscale_source_to_pil(img1, target, resample=resample),
        downscale_source_to_pil(img2, target, resample=resample),
    )
