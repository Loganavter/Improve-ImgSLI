import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import numpy as np
from PIL import Image
from skimage.feature import canny
from skimage.util import img_as_ubyte
from shared.regions import build_uniform_tile_grid

logger = logging.getLogger("ImproveImgSLI")

EDGE_TILE_MAX_EXTENT = 1536
EDGE_MAX_WORKERS = 8

def _resolve_edge_workers(total_tiles: int) -> int:
    if total_tiles <= 1:
        return 1
    cpu_count = os.cpu_count() or 1
    return max(1, min(total_tiles, cpu_count, EDGE_MAX_WORKERS))

def _emit_edge_progress(progress_callback, completed: int, total: int):
    if progress_callback is None or total <= 0:
        return
    payload = {
        "kind": "edge_tiles",
        "completed": completed,
        "total": total,
        "progress": int(completed * 100 / total),
    }
    logger.debug(
        "[EDGE_TOAST_EMIT] completed=%s/%s progress=%s",
        payload["completed"],
        payload["total"],
        payload["progress"],
    )
    progress_callback(payload)

def _compute_edge_tile(
    gray: np.ndarray,
    *,
    tile_index: int,
    total_tiles: int,
    region,
    overlap: int,
    sigma: float,
):
    tile_started_at = time.perf_counter()
    height, width = gray.shape[:2]
    ext_left = max(0, region.left - overlap)
    ext_top = max(0, region.top - overlap)
    ext_right = min(width, region.right + overlap)
    ext_bottom = min(height, region.bottom + overlap)
    gray_tile = gray[ext_top:ext_bottom, ext_left:ext_right]
    edge_tile = canny(gray_tile, sigma=sigma)
    crop_left = region.left - ext_left
    crop_top = region.top - ext_top
    crop_right = crop_left + region.width
    crop_bottom = crop_top + region.height
    edge_patch = img_as_ubyte(edge_tile[crop_top:crop_bottom, crop_left:crop_right])
    return (
        tile_index,
        total_tiles,
        region,
        edge_patch,
        (time.perf_counter() - tile_started_at) * 1000.0,
    )

def create_edge_map(
    image: Image.Image,
    sigma: float = 1.0,
    progress_callback=None,
) -> Optional[Image.Image]:
    if not image:
        return None

    try:
        img_gray = np.array(image.convert("L"))
        height, width = img_gray.shape[:2]
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

        logger.debug(
            "[EDGE_TILES] size=%sx%s grid=%sx%s tile=%sx%s overlap=%s workers=%s parallel=%s",
            width,
            height,
            tile_grid.columns,
            tile_grid.rows,
            tile_grid.tile_width,
            tile_grid.tile_height,
            overlap,
            workers,
            workers > 1,
        )

        completed_tiles = 0
        if workers <= 1:
            for tile_index, region in tile_jobs:
                tile_result = _compute_edge_tile(
                    img_gray,
                    tile_index=tile_index,
                    total_tiles=total_tiles,
                    region=region,
                    overlap=overlap,
                    sigma=sigma,
                )
                completed_tiles += 1
                result[region.top:region.bottom, region.left:region.right] = tile_result[3]
                logger.debug(
                    "[EDGE_TILE] %s/%s completed=%s/%s region=(%s,%s,%s,%s) elapsed_ms=%.1f",
                    tile_result[0],
                    tile_result[1],
                    completed_tiles,
                    total_tiles,
                    region.left,
                    region.top,
                    region.width,
                    region.height,
                    tile_result[4],
                )
                _emit_edge_progress(progress_callback, completed_tiles, total_tiles)
        else:
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="edge-tile") as executor:
                futures = [
                    executor.submit(
                        _compute_edge_tile,
                        img_gray,
                        tile_index=tile_index,
                        total_tiles=total_tiles,
                        region=region,
                        overlap=overlap,
                        sigma=sigma,
                    )
                    for tile_index, region in tile_jobs
                ]
                for future in as_completed(futures):
                    tile_result = future.result()
                    region = tile_result[2]
                    completed_tiles += 1
                    result[region.top:region.bottom, region.left:region.right] = tile_result[3]
                    logger.debug(
                        "[EDGE_TILE] %s/%s completed=%s/%s region=(%s,%s,%s,%s) elapsed_ms=%.1f",
                        tile_result[0],
                        tile_result[1],
                        completed_tiles,
                        total_tiles,
                        region.left,
                        region.top,
                        region.width,
                        region.height,
                        tile_result[4],
                    )
                    _emit_edge_progress(progress_callback, completed_tiles, total_tiles)

        return Image.fromarray(result, mode="L").convert("RGBA")
    except Exception as e:
        logger.error(f"Error creating edge map: {e}", exc_info=True)
        return None
