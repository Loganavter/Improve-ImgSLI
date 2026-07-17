from __future__ import annotations

import logging

from PIL import Image

from shared.analysis.channel_analyzer import extract_channel
from shared.analysis.diff_source import (
    create_edge_map_from_sources,
    create_grayscale_diff_from_sources,
    create_highlight_diff_from_sources,
)
from shared.analysis.differ import (
    create_grayscale_diff,
    create_highlight_diff,
    create_ssim_map,
)
from shared.analysis.edge_detector import create_edge_map
from shared.analysis.ssim_source import create_ssim_map_from_sources
from shared.image_processing.pixel_ops.downscale import downscale_pair_to_limit
from shared.image_processing.store_lease import StoreLease
from shared.image_processing.tiled_pixel_store import TiledPixelStore
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
    *,
    lease1: StoreLease | None = None,
    lease2: StoreLease | None = None,
):
    if isinstance(image1, TiledPixelStore) or isinstance(image2, TiledPixelStore):
        return build_cached_diff_image_from_sources(
            image1,
            image2,
            diff_mode,
            channel_mode=channel_mode,
            optimize_ssim=optimize_ssim,
            progress_callback=progress_callback,
            lease1=lease1,
            lease2=lease2,
        )
    return _build_cached_diff_pil(
        image1,
        image2,
        diff_mode,
        channel_mode=channel_mode,
        optimize_ssim=optimize_ssim,
        progress_callback=progress_callback,
    )


def build_cached_diff_image_from_sources(
    image1,
    image2,
    diff_mode: str,
    channel_mode: str = "RGB",
    optimize_ssim: bool = False,
    progress_callback=None,
    *,
    lease1: StoreLease | None = None,
    lease2: StoreLease | None = None,
):
    if lease1 is not None and not lease1.valid:
        return None
    if lease2 is not None and not lease2.valid:
        return None
    if image1 is None or (image2 is None and diff_mode != "edges"):
        return None

    if diff_mode == "ssim":
        ssim_image1 = image1
        ssim_image2 = image2
        ssim_lease1 = lease1
        ssim_lease2 = lease2
        if optimize_ssim and image2 is not None:
            limit = INTERACTIVE_SSIM_MAX_DIMENSION
            w, h = image1.size
            if max(w, h) > limit or (w * h) > INTERACTIVE_SSIM_MAX_PIXELS:
                ssim_image1, ssim_image2 = downscale_pair_to_limit(
                    image1, image2, limit
                )
                ssim_lease1 = None
                ssim_lease2 = None
        return create_ssim_map_from_sources(
            ssim_image1,
            ssim_image2,
            progress_callback=progress_callback,
            lease1=ssim_lease1,
            lease2=ssim_lease2,
        )

    builders = {
        "edges": lambda: create_edge_map_from_sources(
            image1,
            channel_mode=channel_mode,
            progress_callback=progress_callback,
            lease1=lease1,
        ),
        "highlight": lambda: create_highlight_diff_from_sources(
            image1,
            image2,
            channel_mode=channel_mode,
            progress_callback=progress_callback,
            lease1=lease1,
            lease2=lease2,
        ),
        "grayscale": lambda: create_grayscale_diff_from_sources(
            image1,
            image2,
            channel_mode=channel_mode,
            progress_callback=progress_callback,
            lease1=lease1,
            lease2=lease2,
        ),
    }
    return builders.get(diff_mode, lambda: None)()


def _build_cached_diff_pil(
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
