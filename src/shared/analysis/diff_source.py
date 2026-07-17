"""Tile-fed diff entry points — no full-frame RGB materialization."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import numpy as np
from PIL import Image

from shared.analysis.channel_analyzer import extract_channel
from shared.analysis.differ import (
    _build_diff_tile_jobs,
    _compute_grayscale_tile,
    _compute_rgb_diff_gray_tile,
    _emit_tiled_progress,
    _resolve_ssim_workers,
)
from shared.analysis.edge_detector import (
    EDGE_TILE_MAX_EXTENT,
    _compute_edge_tile,
    _emit_edge_progress,
    _resolve_edge_workers,
)
from shared.image_processing.store_lease import StoreLease
from shared.image_processing.tiled_pixel_store import TiledPixelStore
from shared.regions import build_uniform_tile_grid

logger = logging.getLogger("ImproveImgSLI")

DIFF_SPILL_MAX_DIMENSION = 4096
DIFF_SPILL_MAX_PIXELS = 16_000_000
_BLOCK = 512


def _crop_source(source, box: tuple[int, int, int, int]) -> Image.Image:
    if isinstance(source, TiledPixelStore):
        return source.crop(box)
    return source.crop(box)


def _rgb_array_from_source(source, box: tuple[int, int, int, int]) -> np.ndarray:
    return np.asarray(_crop_source(source, box).convert("RGB"))


def _rgba_from_source(source, box: tuple[int, int, int, int], channel_mode: str) -> Image.Image:
    pil = _crop_source(source, box)
    if channel_mode != "RGB":
        pil = extract_channel(pil, channel_mode) or pil
    return pil.convert("RGBA")


def _align_source2(source1, source2):
    if source2 is None:
        return None
    if source2.size == source1.size:
        return source2
    if isinstance(source2, TiledPixelStore):
        from shared.image_processing.pixel_ops.downscale import downscale_source_to_pil

        return downscale_source_to_pil(source2, source1.size)
    return source2.resize(source1.size, Image.Resampling.LANCZOS)


def finalize_diff_output(
    arr: np.ndarray,
    *,
    channels: int = 1,
) -> Image.Image | TiledPixelStore:
    """Return compact PIL for bounded results, else spill to ``TiledPixelStore``."""
    height, width = arr.shape[:2]
    if (
        width * height <= DIFF_SPILL_MAX_PIXELS
        and max(width, height) <= DIFF_SPILL_MAX_DIMENSION
    ):
        if channels == 1:
            return Image.fromarray(arr, mode="L").convert("RGBA")
        return Image.fromarray(arr, mode="RGB").convert("RGBA")

    store = TiledPixelStore.allocate(width, height)
    try:
        if channels == 1:
            rgba_mode = "L"
        else:
            rgba_mode = "RGB"
        for oy in range(0, height, _BLOCK):
            oy1 = min(oy + _BLOCK, height)
            for ox in range(0, width, _BLOCK):
                ox1 = min(ox + _BLOCK, width)
                patch = arr[oy:oy1, ox:ox1]
                if channels == 1:
                    pil = Image.fromarray(patch, mode="L").convert("RGBA")
                else:
                    pil = Image.fromarray(patch, mode="RGB").convert("RGBA")
                store.write_pil((ox, oy, ox1, oy1), pil)
        return store
    except OSError as exc:
        logger.warning("Diff spill to TiledPixelStore failed, keeping PIL: %s", exc)
        if channels == 1:
            return Image.fromarray(arr, mode="L").convert("RGBA")
        return Image.fromarray(arr, mode="RGB").convert("RGBA")


def create_highlight_diff_from_sources(
    source1,
    source2,
    *,
    threshold: int = 10,
    channel_mode: str = "RGB",
    progress_callback=None,
    lease1: StoreLease | None = None,
    lease2: StoreLease | None = None,
) -> Optional[Image.Image | TiledPixelStore]:
    if lease1 is not None and not lease1.valid:
        return None
    if lease2 is not None and not lease2.valid:
        return None
    if not source1 or not source2:
        return None

    source2 = _align_source2(source1, source2)
    width, height = source1.size
    tile_grid, tile_jobs = _build_diff_tile_jobs(width, height)
    total_tiles = len(tile_jobs)
    workers = _resolve_ssim_workers(total_tiles)
    result = np.empty((height, width, 3), dtype=np.uint8)

    def _process_tile(tile_index: int, region):
        if lease1 is not None and not lease1.valid:
            return None
        if lease2 is not None and not lease2.valid:
            return None
        left, top, right, bottom = region.left, region.top, region.right, region.bottom
        arr1_tile = np.asarray(
            _rgba_from_source(source1, (left, top, right, bottom), channel_mode).convert("RGB")
        )
        arr2_tile = np.asarray(
            _rgba_from_source(source2, (left, top, right, bottom), channel_mode).convert("RGB")
        )
        gray_tile = _compute_rgb_diff_gray_tile(arr1_tile, arr2_tile)
        mask = gray_tile > threshold
        out_tile = arr1_tile.copy()
        out_tile[mask] = (255, 90, 120)
        return region, out_tile

    completed = 0
    if workers <= 1:
        for tile_index, region in tile_jobs:
            patch = _process_tile(tile_index, region)
            if patch is None:
                return None
            region, out_tile = patch
            result[region.top : region.bottom, region.left : region.right] = out_tile
            completed += 1
            _emit_tiled_progress(progress_callback, "highlight_tiles", completed, total_tiles)
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="hl-src") as pool:
            futures = {
                pool.submit(_process_tile, tile_index, region): region
                for tile_index, region in tile_jobs
            }
            for future in as_completed(futures):
                patch = future.result()
                if patch is None:
                    return None
                region, out_tile = patch
                result[region.top : region.bottom, region.left : region.right] = out_tile
                completed += 1
                _emit_tiled_progress(progress_callback, "highlight_tiles", completed, total_tiles)

    _ = tile_grid
    return finalize_diff_output(result, channels=3)


def create_grayscale_diff_from_sources(
    source1,
    source2,
    *,
    channel_mode: str = "RGB",
    progress_callback=None,
    lease1: StoreLease | None = None,
    lease2: StoreLease | None = None,
) -> Optional[Image.Image | TiledPixelStore]:
    if lease1 is not None and not lease1.valid:
        return None
    if lease2 is not None and not lease2.valid:
        return None
    if not source1 or not source2:
        return None

    source2 = _align_source2(source1, source2)
    width, height = source1.size
    _, tile_jobs = _build_diff_tile_jobs(width, height)
    total_tiles = len(tile_jobs)
    workers = _resolve_ssim_workers(total_tiles)
    gray_tiles: dict[int, tuple] = {}
    global_min = 255
    global_max = 0

    def _gray_tile_arrays(region):
        left, top, right, bottom = region.left, region.top, region.right, region.bottom
        arr1 = np.asarray(
            _rgba_from_source(source1, (left, top, right, bottom), channel_mode).convert("RGB")
        )
        arr2 = np.asarray(
            _rgba_from_source(source2, (left, top, right, bottom), channel_mode).convert("RGB")
        )
        return arr1, arr2

    completed = 0
    if workers <= 1:
        for tile_index, region in tile_jobs:
            if lease1 is not None and not lease1.valid:
                return None
            if lease2 is not None and not lease2.valid:
                return None
            arr1, arr2 = _gray_tile_arrays(region)
            entry = _compute_grayscale_tile(tile_index, total_tiles, region, arr1, arr2)
            gray_tiles[tile_index] = entry
            global_min = min(global_min, entry[4])
            global_max = max(global_max, entry[5])
            completed += 1
            _emit_tiled_progress(progress_callback, "grayscale_tiles", completed, total_tiles)
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="gray-src") as pool:
            futures = {
                pool.submit(_gray_tile_arrays, region): (tile_index, region)
                for tile_index, region in tile_jobs
            }
            for future in as_completed(futures):
                if lease1 is not None and not lease1.valid:
                    return None
                if lease2 is not None and not lease2.valid:
                    return None
                tile_index, region = futures[future]
                arr1, arr2 = future.result()
                entry = _compute_grayscale_tile(tile_index, total_tiles, region, arr1, arr2)
                gray_tiles[tile_index] = entry
                global_min = min(global_min, entry[4])
                global_max = max(global_max, entry[5])
                completed += 1
                _emit_tiled_progress(progress_callback, "grayscale_tiles", completed, total_tiles)

    result = np.empty((height, width), dtype=np.uint8)
    scale = None if global_max <= global_min else 255.0 / float(global_max - global_min)
    for tile_index, region in tile_jobs:
        _, _, _, gray_tile, _, _, _ = gray_tiles[tile_index]
        if scale is not None:
            tile_out = np.clip((gray_tile.astype(np.float32) - global_min) * scale, 0.0, 255.0)
            tile_out = tile_out.astype(np.uint8, copy=False)
        else:
            tile_out = gray_tile
        result[region.top : region.bottom, region.left : region.right] = tile_out

    return finalize_diff_output(result, channels=1)


def create_edge_map_from_sources(
    source1,
    *,
    sigma: float = 1.0,
    channel_mode: str = "RGB",
    progress_callback=None,
    lease1: StoreLease | None = None,
) -> Optional[Image.Image | TiledPixelStore]:
    if lease1 is not None and not lease1.valid:
        return None
    if not source1:
        return None

    width, height = source1.size
    overlap = max(8, int(np.ceil(float(sigma) * 6.0)))
    tile_grid = build_uniform_tile_grid(
        width,
        height,
        max_tile_width=EDGE_TILE_MAX_EXTENT,
        max_tile_height=EDGE_TILE_MAX_EXTENT,
    )
    tile_jobs = [
        (tile_index, region)
        for tile_index, (_row, _col, region) in enumerate(tile_grid.iter_regions(), start=1)
    ]
    total_tiles = len(tile_jobs)
    workers = _resolve_edge_workers(total_tiles)
    result = np.empty((height, width), dtype=np.uint8)

    def _gray_crop(box):
        pil = _rgba_from_source(source1, box, channel_mode)
        return np.array(pil.convert("L"))

    def _process_tile(tile_index: int, region):
        if lease1 is not None and not lease1.valid:
            return None
        ext_left = max(0, region.left - overlap)
        ext_top = max(0, region.top - overlap)
        ext_right = min(width, region.right + overlap)
        ext_bottom = min(height, region.bottom + overlap)
        gray_tile = _gray_crop((ext_left, ext_top, ext_right, ext_bottom))
        return _compute_edge_tile(
            gray_tile,
            tile_index=tile_index,
            total_tiles=total_tiles,
            region=region,
            overlap=overlap,
            sigma=sigma,
        )

    completed = 0
    if workers <= 1:
        for tile_index, region in tile_jobs:
            tile_result = _process_tile(tile_index, region)
            if tile_result is None:
                return None
            result[region.top : region.bottom, region.left : region.right] = tile_result[3]
            completed += 1
            _emit_edge_progress(progress_callback, completed, total_tiles)
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="edge-src") as pool:
            futures = {
                pool.submit(_process_tile, tile_index, region): region
                for tile_index, region in tile_jobs
            }
            for future in as_completed(futures):
                tile_result = future.result()
                if tile_result is None:
                    return None
                region = tile_result[2]
                result[region.top : region.bottom, region.left : region.right] = tile_result[3]
                completed += 1
                _emit_edge_progress(progress_callback, completed, total_tiles)

    return finalize_diff_output(result, channels=1)
