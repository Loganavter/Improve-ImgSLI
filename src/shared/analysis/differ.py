import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import numpy as np
from PIL import Image
from shared.regions import build_uniform_tile_grid

logger = logging.getLogger("ImproveImgSLI")

SSIM_DEFAULT_WIN_SIZE = 7
SSIM_TILE_MAX_EXTENT = 1536
SSIM_MAX_WORKERS = 8
DIFF_TILE_MAX_EXTENT = 1536

def _resolve_ssim_win_size(width: int, height: int) -> int:
    win_size = min(SSIM_DEFAULT_WIN_SIZE, width, height)
    if win_size % 2 == 0:
        win_size -= 1
    return max(3, win_size)

def _prepare_ssim_tile_for_output(tile_map: np.ndarray) -> np.ndarray:
    if tile_map.ndim == 3:
        tile_map = np.mean(tile_map, axis=2, dtype=np.float32)
    else:
        tile_map = tile_map.astype(np.float32, copy=False)

    np.subtract(1.0, tile_map, out=tile_map)
    np.multiply(tile_map, 255.0, out=tile_map)
    np.clip(tile_map, 0.0, 255.0, out=tile_map)
    return tile_map.astype(np.uint8, copy=False)

def _resolve_ssim_workers(total_tiles: int) -> int:
    if total_tiles <= 1:
        return 1

    cpu_count = os.cpu_count() or 1
    return max(1, min(total_tiles, cpu_count, SSIM_MAX_WORKERS))

def _emit_tiled_progress(progress_callback, kind: str, completed: int, total: int) -> None:
    if progress_callback is None or total <= 0:
        return
    progress_payload = {
        "kind": kind,
        "completed": completed,
        "total": total,
        "progress": int(completed * 100 / total),
    }
    progress_callback(progress_payload)

def _build_diff_tile_jobs(width: int, height: int):
    tile_grid = build_uniform_tile_grid(
        width,
        height,
        max_tile_width=DIFF_TILE_MAX_EXTENT,
        max_tile_height=DIFF_TILE_MAX_EXTENT,
    )
    tile_jobs = [
        (tile_index, region)
        for tile_index, (_row, _col, region) in enumerate(tile_grid.iter_regions(), start=1)
    ]
    return tile_grid, tile_jobs

def _compute_rgb_diff_gray_tile(arr1_tile: np.ndarray, arr2_tile: np.ndarray) -> np.ndarray:
    diff_tile = np.abs(
        arr1_tile.astype(np.int16, copy=False) - arr2_tile.astype(np.int16, copy=False)
    ).astype(np.float32, copy=False)
    gray_tile = np.rint(
        diff_tile[..., 0] * 0.299
        + diff_tile[..., 1] * 0.587
        + diff_tile[..., 2] * 0.114
    )
    return np.clip(gray_tile, 0.0, 255.0).astype(np.uint8, copy=False)

def _compute_grayscale_tile(tile_index: int, total_tiles: int, region, arr1: np.ndarray, arr2: np.ndarray):
    tile_started_at = time.perf_counter()
    arr1_tile = arr1[region.top:region.bottom, region.left:region.right]
    arr2_tile = arr2[region.top:region.bottom, region.left:region.right]
    gray_tile = _compute_rgb_diff_gray_tile(arr1_tile, arr2_tile)
    return (
        tile_index,
        total_tiles,
        region,
        gray_tile,
        int(gray_tile.min()),
        int(gray_tile.max()),
        (time.perf_counter() - tile_started_at) * 1000.0,
    )

def _compute_tiled_grayscale_diff(
    arr1: np.ndarray,
    arr2: np.ndarray,
    progress_callback=None,
) -> np.ndarray:
    height, width = arr1.shape[:2]
    tile_grid, tile_jobs = _build_diff_tile_jobs(width, height)
    total_tiles = len(tile_jobs)
    workers = _resolve_ssim_workers(total_tiles)
    gray_tiles: dict[int, tuple] = {}
    global_min = 255
    global_max = 0

    logger.debug(
        "[GRAYSCALE_TILES] size=%sx%s grid=%sx%s tile=%sx%s workers=%s parallel=%s",
        width,
        height,
        tile_grid.columns,
        tile_grid.rows,
        tile_grid.tile_width,
        tile_grid.tile_height,
        workers,
        workers > 1,
    )

    completed_tiles = 0
    if workers <= 1:
        for tile_index, region in tile_jobs:
            result = _compute_grayscale_tile(tile_index, total_tiles, region, arr1, arr2)
            gray_tiles[tile_index] = result
            completed_tiles += 1
            global_min = min(global_min, result[4])
            global_max = max(global_max, result[5])
            logger.debug(
                "[GRAYSCALE_TILE] %s/%s completed=%s/%s region=(%s,%s,%s,%s) elapsed_ms=%.1f",
                result[0],
                result[1],
                completed_tiles,
                total_tiles,
                region.left,
                region.top,
                region.width,
                region.height,
                result[6],
            )
            _emit_tiled_progress(progress_callback, "grayscale_tiles", completed_tiles, total_tiles)
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="gray-tile") as executor:
            futures = [
                executor.submit(_compute_grayscale_tile, tile_index, total_tiles, region, arr1, arr2)
                for tile_index, region in tile_jobs
            ]
            for future in as_completed(futures):
                result = future.result()
                region = result[2]
                gray_tiles[result[0]] = result
                completed_tiles += 1
                global_min = min(global_min, result[4])
                global_max = max(global_max, result[5])
                logger.debug(
                    "[GRAYSCALE_TILE] %s/%s completed=%s/%s region=(%s,%s,%s,%s) elapsed_ms=%.1f",
                    result[0],
                    result[1],
                    completed_tiles,
                    total_tiles,
                    region.left,
                    region.top,
                    region.width,
                    region.height,
                    result[6],
                )
                _emit_tiled_progress(progress_callback, "grayscale_tiles", completed_tiles, total_tiles)

    result = np.empty((height, width), dtype=np.uint8)
    scale = None if global_max <= global_min else 255.0 / float(global_max - global_min)
    for tile_index, region in tile_jobs:
        _, _, _, gray_tile, _, _, _ = gray_tiles[tile_index]
        if scale is not None:
            tile_out = np.clip((gray_tile.astype(np.float32) - global_min) * scale, 0.0, 255.0)
            tile_out = tile_out.astype(np.uint8, copy=False)
        else:
            tile_out = gray_tile
        result[region.top:region.bottom, region.left:region.right] = tile_out
    return result

def _compute_highlight_tile(
    tile_index: int,
    total_tiles: int,
    region,
    arr1: np.ndarray,
    arr2: np.ndarray,
    threshold: int,
):
    tile_started_at = time.perf_counter()
    arr1_tile = arr1[region.top:region.bottom, region.left:region.right]
    arr2_tile = arr2[region.top:region.bottom, region.left:region.right]
    gray_tile = _compute_rgb_diff_gray_tile(arr1_tile, arr2_tile)
    mask = gray_tile > threshold
    out_tile = arr1_tile.copy()
    out_tile[mask] = (255, 90, 120)
    return (
        tile_index,
        total_tiles,
        region,
        out_tile,
        (time.perf_counter() - tile_started_at) * 1000.0,
    )

def _compute_tiled_highlight_diff(
    arr1: np.ndarray,
    arr2: np.ndarray,
    *,
    threshold: int,
    progress_callback=None,
) -> np.ndarray:
    height, width = arr1.shape[:2]
    tile_grid, tile_jobs = _build_diff_tile_jobs(width, height)
    total_tiles = len(tile_jobs)
    workers = _resolve_ssim_workers(total_tiles)
    result = np.empty((height, width, 3), dtype=np.uint8)

    logger.debug(
        "[HIGHLIGHT_TILES] size=%sx%s grid=%sx%s tile=%sx%s workers=%s parallel=%s",
        width,
        height,
        tile_grid.columns,
        tile_grid.rows,
        tile_grid.tile_width,
        tile_grid.tile_height,
        workers,
        workers > 1,
    )

    completed_tiles = 0
    if workers <= 1:
        for tile_index, region in tile_jobs:
            result_tuple = _compute_highlight_tile(
                tile_index, total_tiles, region, arr1, arr2, threshold
            )
            completed_tiles += 1
            result[region.top:region.bottom, region.left:region.right] = result_tuple[3]
            logger.debug(
                "[HIGHLIGHT_TILE] %s/%s completed=%s/%s region=(%s,%s,%s,%s) elapsed_ms=%.1f",
                result_tuple[0],
                result_tuple[1],
                completed_tiles,
                total_tiles,
                region.left,
                region.top,
                region.width,
                region.height,
                result_tuple[4],
            )
            _emit_tiled_progress(progress_callback, "highlight_tiles", completed_tiles, total_tiles)
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="highlight-tile") as executor:
            futures = [
                executor.submit(
                    _compute_highlight_tile,
                    tile_index,
                    total_tiles,
                    region,
                    arr1,
                    arr2,
                    threshold,
                )
                for tile_index, region in tile_jobs
            ]
            for future in as_completed(futures):
                result_tuple = future.result()
                region = result_tuple[2]
                completed_tiles += 1
                result[region.top:region.bottom, region.left:region.right] = result_tuple[3]
                logger.debug(
                    "[HIGHLIGHT_TILE] %s/%s completed=%s/%s region=(%s,%s,%s,%s) elapsed_ms=%.1f",
                    result_tuple[0],
                    result_tuple[1],
                    completed_tiles,
                    total_tiles,
                    region.left,
                    region.top,
                    region.width,
                    region.height,
                    result_tuple[4],
                )
                _emit_tiled_progress(progress_callback, "highlight_tiles", completed_tiles, total_tiles)

    return result

def _compute_ssim_tile_patch(
    arr1: np.ndarray,
    arr2: np.ndarray,
    *,
    tile_index: int,
    total_tiles: int,
    region,
    width: int,
    height: int,
    overlap: int,
    win_size: int,
):
    from skimage.metrics import structural_similarity as ssim

    tile_started_at = time.perf_counter()
    ext_left = max(0, region.left - overlap)
    ext_top = max(0, region.top - overlap)
    ext_right = min(width, region.right + overlap)
    ext_bottom = min(height, region.bottom + overlap)

    arr1_tile = arr1[ext_top:ext_bottom, ext_left:ext_right]
    arr2_tile = arr2[ext_top:ext_bottom, ext_left:ext_right]

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

    return (
        tile_index,
        total_tiles,
        region,
        _prepare_ssim_tile_for_output(tile_patch),
        (time.perf_counter() - tile_started_at) * 1000.0,
    )

def _compute_ssim_diff_gray_tiled(
    arr1: np.ndarray,
    arr2: np.ndarray,
    progress_callback=None,
) -> np.ndarray:
    height, width = arr1.shape[:2]
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

    logger.debug(
        "[SSIM_TILES] size=%sx%s grid=%sx%s tile=%sx%s win=%s overlap=%s workers=%s parallel=%s",
        width,
        height,
        tile_grid.columns,
        tile_grid.rows,
        tile_grid.tile_width,
        tile_grid.tile_height,
        win_size,
        overlap,
        workers,
        workers > 1,
    )

    tiles_started_at = time.perf_counter()
    tile_jobs = [
        (tile_index, region)
        for tile_index, (_row, _col, region) in enumerate(tile_grid.iter_regions(), start=1)
    ]

    if workers <= 1:
        completed_tiles = 0
        for tile_index, region in tile_jobs:
            (
                tile_index,
                total_tiles,
                region,
                tile_patch,
                tile_elapsed_ms,
            ) = _compute_ssim_tile_patch(
                arr1,
                arr2,
                tile_index=tile_index,
                total_tiles=total_tiles,
                region=region,
                width=width,
                height=height,
                overlap=overlap,
                win_size=win_size,
            )
            completed_tiles += 1
            result[region.top:region.bottom, region.left:region.right] = tile_patch

            logger.debug(
                "[SSIM_TILE] %s/%s completed=%s/%s region=(%s,%s,%s,%s) elapsed_ms=%.1f",
                tile_index,
                total_tiles,
                completed_tiles,
                total_tiles,
                region.left,
                region.top,
                region.width,
                region.height,
                tile_elapsed_ms,
            )
            if progress_callback is not None:
                progress_payload = {
                    "kind": "ssim_tiles",
                    "completed": completed_tiles,
                    "total": total_tiles,
                    "progress": int(completed_tiles * 100 / total_tiles),
                }
                progress_callback(progress_payload)
    else:
        completed_tiles = 0
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ssim-tile") as executor:
            futures = [
                executor.submit(
                    _compute_ssim_tile_patch,
                    arr1,
                    arr2,
                    tile_index=tile_index,
                    total_tiles=total_tiles,
                    region=region,
                    width=width,
                    height=height,
                    overlap=overlap,
                    win_size=win_size,
                )
                for tile_index, region in tile_jobs
            ]
            for future in as_completed(futures):
                (
                    tile_index,
                    total_tiles,
                    region,
                    tile_patch,
                    tile_elapsed_ms,
                ) = future.result()
                completed_tiles += 1
                result[region.top:region.bottom, region.left:region.right] = tile_patch

                logger.debug(
                    "[SSIM_TILE] %s/%s completed=%s/%s region=(%s,%s,%s,%s) elapsed_ms=%.1f",
                    tile_index,
                    total_tiles,
                    completed_tiles,
                    total_tiles,
                    region.left,
                    region.top,
                    region.width,
                    region.height,
                    tile_elapsed_ms,
                )
                if progress_callback is not None:
                    progress_payload = {
                        "kind": "ssim_tiles",
                        "completed": completed_tiles,
                        "total": total_tiles,
                        "progress": int(completed_tiles * 100 / total_tiles),
                    }
                    progress_callback(progress_payload)

    logger.debug(
        "[SSIM_TILES_DONE] total_tiles=%s workers=%s elapsed_ms=%.1f",
        total_tiles,
        workers,
        (time.perf_counter() - tiles_started_at) * 1000.0,
    )
    return result

def create_highlight_diff(
    image1: Image.Image,
    image2: Image.Image,
    threshold: int = 20,
    font_path: Optional[str] = None,
    progress_callback=None,
) -> Optional[Image.Image]:
    """
    Создает изображение с подсвеченными различиями красным цветом.
    """
    if not image1 or not image2:
        return None

    if image1.size != image2.size:
        try:
            image2 = image2.resize(image1.size, Image.Resampling.LANCZOS)
        except Exception:
            return None

    try:
        arr1 = np.asarray(image1.convert("RGB"))
        arr2 = np.asarray(image2.convert("RGB"))
        result = _compute_tiled_highlight_diff(
            arr1,
            arr2,
            threshold=threshold,
            progress_callback=progress_callback,
        )
        return Image.fromarray(result, mode="RGB").convert("RGBA")
    except Exception as e:
        logger.error(f"Error creating highlight diff: {e}", exc_info=True)
        return None

def create_grayscale_diff(
    image1: Image.Image,
    image2: Image.Image,
    font_path: Optional[str] = None,
    progress_callback=None,
) -> Optional[Image.Image]:
    """
    Создает изображение различий в градациях серого.
    Усилен контраст для наглядности.
    """
    if not image1 or not image2:
        return None

    if image1.size != image2.size:
        try:
            image2 = image2.resize(image1.size, Image.Resampling.LANCZOS)
        except Exception:
            return None

    try:
        arr1 = np.asarray(image1.convert("RGB"))
        arr2 = np.asarray(image2.convert("RGB"))
        diff_gray = _compute_tiled_grayscale_diff(
            arr1,
            arr2,
            progress_callback=progress_callback,
        )
        return Image.fromarray(diff_gray, mode="L").convert("RGBA")
    except Exception as e:
        logger.error(f"Error creating grayscale diff: {e}", exc_info=True)
        return None

def create_ssim_map(
    image1: Image.Image,
    image2: Image.Image,
    font_path: Optional[str] = None,
    progress_callback=None,
) -> Optional[Image.Image]:
    """
    Создает карту структурного сходства (SSIM).
    """
    if not image1 or not image2:
        return None

    if image1.size != image2.size:
        try:
            image2 = image2.resize(image1.size, Image.Resampling.LANCZOS)
        except Exception:
            return None

    total_started_at = time.perf_counter()
    try:
        convert_started_at = time.perf_counter()
        arr1 = np.asarray(image1.convert("RGB"))
        arr2 = np.asarray(image2.convert("RGB"))
        convert_elapsed_ms = (time.perf_counter() - convert_started_at) * 1000.0

        ssim_started_at = time.perf_counter()
        heatmap_gray = _compute_ssim_diff_gray_tiled(
            arr1,
            arr2,
            progress_callback=progress_callback,
        )
        ssim_elapsed_ms = (time.perf_counter() - ssim_started_at) * 1000.0

        post_started_at = time.perf_counter()
        post_elapsed_ms = (time.perf_counter() - post_started_at) * 1000.0

        total_elapsed_ms = (time.perf_counter() - total_started_at) * 1000.0
        logger.debug(
            "[SSIM] size=%sx%s convert_ms=%.1f ssim_ms=%.1f post_ms=%.1f total_ms=%.1f",
            image1.width,
            image1.height,
            convert_elapsed_ms,
            ssim_elapsed_ms,
            post_elapsed_ms,
            total_elapsed_ms,
        )

        return Image.fromarray(heatmap_gray, mode="L").convert("RGBA")

    except Exception as e:
        logger.error(f"Error creating SSIM map: {e}", exc_info=True)
        return None
