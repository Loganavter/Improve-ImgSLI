from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from PIL import Image

from shared.image_processing.autocrop.model import CropBox

@dataclass(frozen=True)
class PreparedAnalysisPair:
    image1: Image.Image
    image2: Image.Image | None
    resized: bool
    original_size1: tuple[int, int] | None
    original_size2: tuple[int, int] | None

def align_analysis_pair(
    image1: Image.Image,
    image2: Image.Image | None,
    *,
    resample: Image.Resampling = Image.Resampling.LANCZOS,
) -> PreparedAnalysisPair:
    if image2 is None or image1.size == image2.size:
        return PreparedAnalysisPair(
            image1=image1,
            image2=image2,
            resized=False,
            original_size1=getattr(image1, "size", None),
            original_size2=getattr(image2, "size", None),
        )

    return PreparedAnalysisPair(
        image1=image1,
        image2=image2.resize(image1.size, resample),
        resized=True,
        original_size1=getattr(image1, "size", None),
        original_size2=getattr(image2, "size", None),
    )

def limit_analysis_pair_size(
    image1: Image.Image,
    image2: Image.Image | None,
    *,
    max_dimension: int | None = None,
    max_pixels: int | None = None,
    resample: Image.Resampling = Image.Resampling.LANCZOS,
) -> PreparedAnalysisPair:
    if image1 is None:
        return PreparedAnalysisPair(
            image1=image1,
            image2=image2,
            resized=False,
            original_size1=None,
            original_size2=getattr(image2, "size", None),
        )

    width, height = image1.size
    scale = 1.0

    if max_dimension and max(width, height) > int(max_dimension):
        scale = min(scale, float(max_dimension) / float(max(width, height)))

    if max_pixels and (width * height) > int(max_pixels):
        scale = min(scale, math.sqrt(float(max_pixels) / float(width * height)))

    if scale >= 0.999999:
        return PreparedAnalysisPair(
            image1=image1,
            image2=image2,
            resized=False,
            original_size1=getattr(image1, "size", None),
            original_size2=getattr(image2, "size", None),
        )

    target_size = (
        max(1, int(round(width * scale))),
        max(1, int(round(height * scale))),
    )
    resized_image1 = image1.resize(target_size, resample)
    resized_image2 = (
        None if image2 is None else image2.resize(target_size, resample)
    )
    return PreparedAnalysisPair(
        image1=resized_image1,
        image2=resized_image2,
        resized=True,
        original_size1=getattr(image1, "size", None),
        original_size2=getattr(image2, "size", None),
    )

def prepare_pair_for_global_analysis(
    image1: Image.Image,
    image2: Image.Image | None,
    *,
    max_dimension: int | None = None,
    max_pixels: int | None = None,
    resample: Image.Resampling = Image.Resampling.LANCZOS,
) -> PreparedAnalysisPair:
    aligned = align_analysis_pair(image1, image2, resample=resample)
    return limit_analysis_pair_size(
        aligned.image1,
        aligned.image2,
        max_dimension=max_dimension,
        max_pixels=max_pixels,
        resample=resample,
    )


def resolve_crop_boxes_for_paths(
    path1: str | None,
    path2: str | None,
    get_crop_service: Any | None = None,
) -> tuple[CropBox | None, CropBox | None]:
    """Detected crop windows for a comparison pair (W3c box-aware analysis).

    Single sanctioned resolution path: :func:`effective_crop_box_for_path`
    (the single owner in ``pipeline/crop_box.py``) — never ``CropService.get``
    here. ``get_crop_service`` is an optional zero-arg callable returning the
    session detection service (``controller._get_crop_service()`` — ``None``
    when autocrop is OFF); unset/``None`` service → ``(None, None)`` and every
    consumer below keeps today's full-frame behavior. ``override`` stays
    reserved for the later per-image wave — never passed.
    """
    if get_crop_service is None:
        return None, None
    try:
        service = get_crop_service() if callable(get_crop_service) else get_crop_service
    except Exception:
        return None, None
    if service is None:
        return None, None
    from tabs.image_compare.pipeline.crop_box import effective_crop_box_for_path

    try:
        box1 = effective_crop_box_for_path(path1, crop_service=service) if path1 else None
    except Exception:
        box1 = None
    try:
        box2 = effective_crop_box_for_path(path2, crop_service=service) if path2 else None
    except Exception:
        box2 = None
    return box1, box2


def crop_source_to_box(source: Any, box: CropBox | None) -> Any:
    """Crop a full-frame source to its detected crop window (W3c).

    ``None`` box → ``source`` untouched (identical object, no copy), so the
    None-box path is byte-identical to today's full-frame behavior. The box
    must fit inside the source: a source smaller than the box is a downscaled
    preview tier, not the full frame the box was detected in — leave it
    untouched rather than cropping wrong coordinates. Region reads go through
    :meth:`TiledPixelStore.crop` (window-only copy, never full materialize).
    """
    if source is None or box is None:
        return source
    try:
        from shared.image_processing.tiled_pixel_store import pixel_source_size

        w, h = pixel_source_size(source)
    except Exception:
        return source
    if w <= 0 or h <= 0:
        return source
    try:
        left, top, right, bottom = (
            int(box.left),
            int(box.top),
            int(box.right),
            int(box.bottom),
        )
    except Exception:
        return source
    # Box detected in full-source coords: a smaller source is a preview tier.
    if right > w or bottom > h:
        return source
    left = max(0, left)
    top = max(0, top)
    right = min(w, right)
    bottom = min(h, bottom)
    if left >= right or top >= bottom:
        return source
    if left == 0 and top == 0 and right == w and bottom == h:
        return source
    try:
        from shared.image_processing.pixel_ops.resample import crop_source

        return crop_source(source, (left, top, right, bottom))
    except Exception:
        return source


def crop_pair_to_boxes(
    image1: Any,
    image2: Any | None,
    box1: CropBox | None,
    box2: CropBox | None,
) -> tuple[Any, Any | None]:
    """Crop both sides of a comparison pair to their crop windows (W3c).

    Both boxes ``None`` → inputs returned untouched (today's behavior).
    ``image2`` may be ``None`` (edges mode) — passed through.
    """
    if box1 is None and box2 is None:
        return image1, image2
    return (
        crop_source_to_box(image1, box1),
        image2 if image2 is None else crop_source_to_box(image2, box2),
    )