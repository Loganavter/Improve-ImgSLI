"""Pre-scale image pairs to a target output size.

Used by video export and preview rendering to avoid processing
full-resolution images when the output is much smaller.
"""
from __future__ import annotations

from PIL import Image

def prescale_pair(
    img1: Image.Image | None,
    img2: Image.Image | None,
    output_width: int,
    output_height: int,
) -> tuple[Image.Image | None, Image.Image | None]:
    """Downscale *img1* and *img2* so they fit within *output_width* x *output_height*.

    If the images are already smaller than (or equal to) the output, they are
    returned unchanged.  Both images are scaled by the same factor so that
    aspect ratio and relative sizing are preserved.

    Returns the (possibly resized) pair.
    """
    if img1 is None or img2 is None:
        return img1, img2

    src_w = max(img1.width, img2.width)
    src_h = max(img1.height, img2.height)

    if src_w <= output_width and src_h <= output_height:
        return img1, img2

    ratio = min(output_width / src_w, output_height / src_h)
    if ratio >= 1.0:
        return img1, img2

    def _resize(img: Image.Image) -> Image.Image:
        new_w = max(1, int(img.width * ratio))
        new_h = max(1, int(img.height * ratio))
        return img.resize((new_w, new_h), Image.Resampling.BILINEAR)

    return _resize(img1), _resize(img2)
