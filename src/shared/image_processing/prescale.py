"""Pre-scale image pairs to a target output size.

Used by video export and preview rendering to avoid processing
full-resolution images when the output is much smaller.
"""
from __future__ import annotations

from PIL import Image

from shared.image_processing.resize import resample_image

def prescale_pair(
    img1: Image.Image | None,
    img2: Image.Image | None,
    output_width: int,
    output_height: int,
    method_name: str = "LANCZOS",
) -> tuple[Image.Image | None, Image.Image | None]:
    """Scale *img1* and *img2* to one shared size within the output bounds.

    Export/render paths need the pair unified before the canvas plan is built.
    If a high-res/low-res pair is scaled by one shared ratio first, the low-res
    image can become tiny and then get upscaled again by the unification step.
    Instead, compute the output size from the largest source dimensions and
    resize both images directly to that final shared size.

    Returns the (possibly resized) pair.
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

    def _resize(img: Image.Image) -> Image.Image:
        if img.size == target_size:
            return img
        return resample_image(
            img,
            target_size,
            method_name,
            is_interactive_render=False,
        )

    return _resize(img1), _resize(img2)
