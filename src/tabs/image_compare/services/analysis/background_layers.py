from __future__ import annotations

import logging

from PIL import Image

from shared.analysis.channel_analyzer import extract_channel
from shared.analysis.differ import (
    create_grayscale_diff,
    create_highlight_diff,
    create_ssim_map,
)
from shared.analysis.edge_detector import create_edge_map
from tabs.image_compare.services.analysis.analysis_pair import (
    prepare_pair_for_global_analysis,
)

logger = logging.getLogger("ImproveImgSLI")

INTERACTIVE_SSIM_MAX_DIMENSION = 2048
INTERACTIVE_SSIM_MAX_PIXELS = 4_000_000

def build_cached_diff_image(
    image1,
    image2,
    diff_mode: str,
    channel_mode: str = "RGB",
    optimize_ssim: bool = False,
    progress_callback=None,
):
    if image1 is None or (image2 is None and diff_mode != "edges"):
        return None

    processed1 = image1
    processed2 = image2

    if channel_mode != "RGB":
        processed1 = extract_channel(processed1, channel_mode) or processed1
        if processed2 is not None:
            processed2 = extract_channel(processed2, channel_mode) or processed2

    prepared_image2 = processed2
    if processed2 is not None and processed2.size != processed1.size:
        prepared_image2 = processed2.resize(processed1.size, Image.Resampling.LANCZOS)

    ssim_image1 = processed1
    ssim_image2 = prepared_image2
    if diff_mode == "ssim" and optimize_ssim and prepared_image2 is not None:
        prepared_pair = prepare_pair_for_global_analysis(
            processed1,
            prepared_image2,
            max_dimension=INTERACTIVE_SSIM_MAX_DIMENSION,
            max_pixels=INTERACTIVE_SSIM_MAX_PIXELS,
        )
        ssim_image1 = prepared_pair.image1
        ssim_image2 = prepared_pair.image2
        if prepared_pair.resized:
            logger.debug(
                "[SSIM_PLAN] optimized=True size1=%s size2=%s prepared1=%s prepared2=%s",
                getattr(processed1, "size", None),
                getattr(prepared_image2, "size", None),
                getattr(ssim_image1, "size", None),
                getattr(ssim_image2, "size", None),
            )

    builders = {
        "edges": lambda: create_edge_map(
            processed1,
            progress_callback=progress_callback,
        ),
        "highlight": lambda: create_highlight_diff(
            processed1,
            prepared_image2,
            threshold=10,
            progress_callback=progress_callback,
        ),
        "grayscale": lambda: create_grayscale_diff(
            processed1,
            prepared_image2,
            progress_callback=progress_callback,
        ),
        "ssim": lambda: create_ssim_map(
            ssim_image1,
            ssim_image2,
            progress_callback=progress_callback,
        ),
    }
    return builders.get(diff_mode, lambda: None)()
