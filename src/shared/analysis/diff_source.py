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
    _compute_rgb_diff_gray_tile,
    _emit_tiled_progress,
    _resolve_ssim_workers,
    resample_second_to_first,
)
from shared.analysis.edge_detector import (
    EDGE_TILE_MAX_EXTENT,
    _compute_edge_tile,
    _emit_edge_progress,
    _resolve_edge_workers,
)
from shared.analysis.output import open_streaming_output, to_u8_rgb
from shared.image_processing.store_lease import StoreLease
from engine.store.tiled_pixel_store import TiledPixelStore
from engine.store.regions import build_uniform_tile_grid
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


class _LeaseAborted(Exception):
    """Control-flow abort: a lease went stale mid-read (post-read re-check).

    Raised instead of returning a torn tile; every tile loop catches it
    (alongside read-time ``RuntimeError``) and returns ``None`` like any
    other abort — never propagates to callers.
    """


def _crop_source(source, box: tuple[int, int, int, int]) -> Image.Image:
    if isinstance(source, TiledPixelStore):
        return source.crop(box)
    return source.crop(box)


def _rgb_array_from_source(source, box: tuple[int, int, int, int]) -> np.ndarray:
    # 16-bit PIL sources scale //257 here, never clip/truncate.
    return np.asarray(to_u8_rgb(_crop_source(source, box)))


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
        from engine.store.pixel_ops.downscale import downscale_source_to_pil

        logger.debug(
            "[ANALYSIS_ALIGN] resampled store source2 %s -> %s (downscale; map+scalar policy)",
            source2.size,
            source1.size,
        )
        return downscale_source_to_pil(source2, source1.size)
    # PIL leg shares the ONE map+scalar policy (resample-and-record).
    _, aligned, _ = resample_second_to_first(source1, source2)
    return aligned


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
    if not StoreLease.guard(lease1, lease2):
        return None
    if not source1 or not source2:
        return None

    source2 = _align_source2(source1, source2)
    # Align reads the stores (downscale/resample): re-guard the window —
    # a close during align must abort, not flow into the tile loops.
    if not StoreLease.guard(lease1, lease2):
        return None
    # Pin the guarded stores across the compute window (strong refs held
    # in these locals for the whole function; tile loops still re-guard
    # before and after every read — see StoreLease's check-use contract).
    _pinned1 = lease1.pinned() if lease1 is not None else None
    _pinned2 = lease2.pinned() if lease2 is not None else None
    width, height = source1.size
    tile_grid, tile_jobs = _build_diff_tile_jobs(width, height)
    total_tiles = len(tile_jobs)
    workers = _resolve_ssim_workers(total_tiles)
    # Tile-streamed output (no full-frame result): patches land in the
    # writer as they complete, RAM or spill store as decided by size.
    writer = open_streaming_output(width, height, channels=3)

    def _process_tile(tile_index: int, region):
        if StoreLease.any_stale(lease1, lease2):
            return None
        left, top, right, bottom = region.left, region.top, region.right, region.bottom
        arr1_tile = np.asarray(
            to_u8_rgb(_rgba_from_source(source1, (left, top, right, bottom), channel_mode))
        )
        arr2_tile = np.asarray(
            to_u8_rgb(_rgba_from_source(source2, (left, top, right, bottom), channel_mode))
        )
        if StoreLease.any_stale(lease1, lease2):
            return None
        gray_tile = _compute_rgb_diff_gray_tile(arr1_tile, arr2_tile)
        mask = gray_tile > threshold
        out_tile = arr1_tile.copy()
        out_tile[mask] = (255, 90, 120)
        return region, out_tile

    completed = 0
    if workers <= 1:
        for tile_index, region in tile_jobs:
            try:
                patch = _process_tile(tile_index, region)
            except RuntimeError:
                # Store closed mid-read (check-use race): abort like a
                # stale lease, never propagate torn state.
                return None
            if patch is None:
                return None
            region, out_tile = patch
            writer.write_tile(
                (region.left, region.top, region.right, region.bottom), out_tile
            )
            completed += 1
            _emit_tiled_progress(progress_callback, "highlight_tiles", completed, total_tiles)
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="hl-src") as pool:
            futures = {
                pool.submit(_process_tile, tile_index, region): region
                for tile_index, region in tile_jobs
            }
            for future in as_completed(futures):
                try:
                    patch = future.result()
                except RuntimeError:
                    return None
                if patch is None or StoreLease.any_stale(lease1, lease2):
                    return None
                region, out_tile = patch
                writer.write_tile(
                    (region.left, region.top, region.right, region.bottom), out_tile
                )
                completed += 1
                _emit_tiled_progress(progress_callback, "highlight_tiles", completed, total_tiles)

    _ = tile_grid
    _ = _pinned1, _pinned2
    return writer.finalize()


def create_grayscale_diff_from_sources(
    source1,
    source2,
    *,
    channel_mode: str = "RGB",
    progress_callback=None,
    lease1: StoreLease | None = None,
    lease2: StoreLease | None = None,
) -> Optional[Image.Image | TiledPixelStore]:
    if not StoreLease.guard(lease1, lease2):
        return None
    if not source1 or not source2:
        return None

    source2 = _align_source2(source1, source2)
    if not StoreLease.guard(lease1, lease2):
        return None
    _pinned1 = lease1.pinned() if lease1 is not None else None
    _pinned2 = lease2.pinned() if lease2 is not None else None
    width, height = source1.size
    _, tile_jobs = _build_diff_tile_jobs(width, height)
    total_tiles = len(tile_jobs)
    workers = _resolve_ssim_workers(total_tiles)
    # Pass 1 scans tile extrema only (tiles discarded, never stored): the
    # global linear normalize needs min/max first, and a per-tile dict is
    # a full frame in RAM.
    global_min = 255
    global_max = 0

    def _gray_tile_arrays(region):
        left, top, right, bottom = region.left, region.top, region.right, region.bottom
        arr1 = np.asarray(
            to_u8_rgb(_rgba_from_source(source1, (left, top, right, bottom), channel_mode))
        )
        arr2 = np.asarray(
            to_u8_rgb(_rgba_from_source(source2, (left, top, right, bottom), channel_mode))
        )
        if StoreLease.any_stale(lease1, lease2):
            raise _LeaseAborted
        return arr1, arr2

    def _gray_extrema(arr1, arr2):
        # Tile-local kernel (no full-image region slicing: inputs here are
        # already per-tile crops, unlike differ's full-array path).
        gray_tile = _compute_rgb_diff_gray_tile(arr1, arr2)
        return gray_tile, int(gray_tile.min()), int(gray_tile.max())

    completed = 0
    if workers <= 1:
        for tile_index, region in tile_jobs:
            if StoreLease.any_stale(lease1, lease2):
                return None
            try:
                arr1, arr2 = _gray_tile_arrays(region)
            except (RuntimeError, _LeaseAborted):
                return None
            _, tile_min, tile_max = _gray_extrema(arr1, arr2)
            global_min = min(global_min, tile_min)
            global_max = max(global_max, tile_max)
            completed += 1
            _emit_tiled_progress(progress_callback, "grayscale_tiles", completed, total_tiles)
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="gray-src") as pool:
            futures = {
                pool.submit(_gray_tile_arrays, region): (tile_index, region)
                for tile_index, region in tile_jobs
            }
            for future in as_completed(futures):
                if StoreLease.any_stale(lease1, lease2):
                    return None
                tile_index, region = futures[future]
                try:
                    arr1, arr2 = future.result()
                except (RuntimeError, _LeaseAborted):
                    return None
                _, tile_min, tile_max = _gray_extrema(arr1, arr2)
                global_min = min(global_min, tile_min)
                global_max = max(global_max, tile_max)
                completed += 1
                _emit_tiled_progress(progress_callback, "grayscale_tiles", completed, total_tiles)

    # Pass 2 recomputes each tile (cheap re-crop + numpy kernels) and
    # streams it scaled into the output writer: peak RAM stays at tile
    # scale instead of holding every tile plus the full result.
    scale = None if global_max <= global_min else 255.0 / float(global_max - global_min)
    writer = open_streaming_output(width, height, channels=1)
    for tile_index, region in tile_jobs:
        if StoreLease.any_stale(lease1, lease2):
            return None
        try:
            arr1, arr2 = _gray_tile_arrays(region)
        except (RuntimeError, _LeaseAborted):
            return None
        gray_tile, _, _ = _gray_extrema(arr1, arr2)
        if scale is not None:
            tile_out = np.clip((gray_tile.astype(np.float32) - global_min) * scale, 0.0, 255.0)
            tile_out = tile_out.astype(np.uint8, copy=False)
        else:
            tile_out = gray_tile
        writer.write_tile(
            (region.left, region.top, region.right, region.bottom), tile_out
        )

    _ = _pinned1, _pinned2
    return writer.finalize()


def create_edge_map_from_sources(
    source1,
    *,
    sigma: float = 1.0,
    channel_mode: str = "RGB",
    progress_callback=None,
    lease1: StoreLease | None = None,
) -> Optional[Image.Image | TiledPixelStore]:
    if not StoreLease.guard(lease1):
        return None
    if not source1:
        return None
    _pinned1 = lease1.pinned() if lease1 is not None else None

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
    # Tile-streamed output (no full-frame result): patches land in the
    # writer as they complete, RAM or spill store as decided by size.
    writer = open_streaming_output(width, height, channels=1)

    def _gray_crop(box):
        pil = _rgba_from_source(source1, box, channel_mode)
        return np.array(to_u8_rgb(pil).convert("L"))

    def _process_tile(tile_index: int, region):
        if StoreLease.any_stale(lease1):
            return None
        ext_left = max(0, region.left - overlap)
        ext_top = max(0, region.top - overlap)
        ext_right = min(width, region.right + overlap)
        ext_bottom = min(height, region.bottom + overlap)
        gray_tile = _gray_crop((ext_left, ext_top, ext_right, ext_bottom))
        if StoreLease.any_stale(lease1):
            return None
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
            try:
                tile_result = _process_tile(tile_index, region)
            except RuntimeError:
                return None
            if tile_result is None:
                return None
            region = tile_result[2]
            writer.write_tile(
                (region.left, region.top, region.right, region.bottom), tile_result[3]
            )
            completed += 1
            _emit_edge_progress(progress_callback, completed, total_tiles)
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="edge-src") as pool:
            futures = {
                pool.submit(_process_tile, tile_index, region): region
                for tile_index, region in tile_jobs
            }
            for future in as_completed(futures):
                try:
                    tile_result = future.result()
                except RuntimeError:
                    return None
                if tile_result is None or StoreLease.any_stale(lease1):
                    return None
                region = tile_result[2]
                writer.write_tile(
                    (region.left, region.top, region.right, region.bottom), tile_result[3]
                )
                completed += 1
                _emit_edge_progress(progress_callback, completed, total_tiles)

    _ = _pinned1
    return writer.finalize()