"""Tile-fed SSIM entry points — no full-frame RGB materialization."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import numpy as np
from PIL import Image

from shared.image_processing.store_lease import StoreLease
from shared.image_processing.tiled_pixel_store import TiledPixelStore
from shared.regions import build_uniform_tile_grid
from shared.analysis.differ import (
    SSIM_TILE_MAX_EXTENT,
    _prepare_ssim_tile_for_output,
    _resolve_ssim_win_size,
    _resolve_ssim_workers,
)

logger = logging.getLogger("ImproveImgSLI")


def _rgb_array_from_source(source, box: tuple[int, int, int, int]) -> np.ndarray:
    if isinstance(source, TiledPixelStore):
        pil = source.crop(box)
    else:
        pil = source.crop(box)
    return np.asarray(pil.convert("RGB"))


def _align_source2(source1, source2):
    if source2 is None:
        return None
    if source2.size == source1.size:
        return source2
    if isinstance(source2, TiledPixelStore):
        from shared.image_processing.pixel_ops.downscale import downscale_source_to_pil

        return downscale_source_to_pil(source2, source1.size)
    return source2.resize(source1.size, Image.Resampling.LANCZOS)


def create_ssim_map_from_sources(
    source1,
    source2,
    *,
    font_path: Optional[str] = None,
    progress_callback=None,
    lease1: StoreLease | None = None,
    lease2: StoreLease | None = None,
) -> Optional[Image.Image]:
    if lease1 is not None and not lease1.valid:
        return None
    if lease2 is not None and not lease2.valid:
        return None
    if not source1 or not source2:
        return None

    source2 = _align_source2(source1, source2)
    width, height = source1.size
    win_size = _resolve_ssim_win_size(width, height)
    overlap = max(1, win_size // 2)
    tile_grid = build_uniform_tile_grid(
        width,
        height,
        max_tile_width=SSIM_TILE_MAX_EXTENT,
        max_tile_height=SSIM_TILE_MAX_EXTENT,
    )
    result = np.empty((height, width), dtype=np.uint8)
    total_tiles = tile_grid.rows * tile_grid.columns
    workers = _resolve_ssim_workers(total_tiles)
    total_started_at = time.perf_counter()

    def _process_tile(tile_index: int, region):
        if lease1 is not None and not lease1.valid:
            return None
        if lease2 is not None and not lease2.valid:
            return None
        from skimage.metrics import structural_similarity as ssim

        ext_left = max(0, region.left - overlap)
        ext_top = max(0, region.top - overlap)
        ext_right = min(width, region.right + overlap)
        ext_bottom = min(height, region.bottom + overlap)
        arr1_tile = _rgb_array_from_source(source1, (ext_left, ext_top, ext_right, ext_bottom))
        arr2_tile = _rgb_array_from_source(
            source2, (ext_left, ext_top, ext_right, ext_bottom)
        )
        _, tile_map = ssim(
            arr1_tile,
            arr2_tile,
            full=True,
            channel_axis=-1,
            data_range=255,
            win_size=win_size,
        )
        crop_left = region.left - ext_left
        crop_top = region.top - ext_top
        crop_right = crop_left + region.width
        crop_bottom = crop_top + region.height
        tile_patch = tile_map[crop_top:crop_bottom, crop_left:crop_right]
        return region, _prepare_ssim_tile_for_output(tile_patch)

    tile_jobs = [
        (tile_index, region)
        for tile_index, (_row, _col, region) in enumerate(tile_grid.iter_regions(), start=1)
    ]

    if workers <= 1:
        for tile_index, region in tile_jobs:
            patch_result = _process_tile(tile_index, region)
            if patch_result is None:
                return None
            region, tile_patch = patch_result
            result[region.top : region.bottom, region.left : region.right] = tile_patch
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ssim-src") as pool:
            futures = {
                pool.submit(_process_tile, tile_index, region): region
                for tile_index, region in tile_jobs
            }
            for future in as_completed(futures):
                patch_result = future.result()
                if patch_result is None:
                    return None
                region, tile_patch = patch_result
                result[region.top : region.bottom, region.left : region.right] = tile_patch

    logger.debug(
        "[SSIM_SRC] size=%sx%s elapsed_ms=%.1f",
        width,
        height,
        (time.perf_counter() - total_started_at) * 1000.0,
    )
    _ = font_path
    from shared.analysis.diff_source import finalize_diff_output

    return finalize_diff_output(result, channels=1)
