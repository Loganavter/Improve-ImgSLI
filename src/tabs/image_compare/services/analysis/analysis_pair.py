from __future__ import annotations

import math
from dataclasses import dataclass

from PIL import Image

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
