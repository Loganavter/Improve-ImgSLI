"""Tiled full-resolution artifact runner.

The gallery's stage-2 catalog runs on a bounded proxy (longest edge <= 1024),
which is fine for a quick triage but loses exactly the artifacts that only
exist at full resolution: the 8x8 DCT block grid is destroyed by the
downscale (so blocking reads clean) and a 1-2 px chroma rim is averaged into
its surroundings (so fringing reads clean). This runner walks the
full-resolution source tile-by-tile, runs the *existing* ``analyze_images``
detectors per tile — they stay the single implementation — and aggregates the
worst-of-tiles severity per artifact.

Two invariants keep the detectors honest:

- **No implicit downscale.** ``artifacts._to_gray_array`` / ``_to_rgb_arrays``
  resize any array whose longest edge exceeds 512, which corrupts the 8x8
  block grid and averages thin rims away. Every cropped tile (core + apron)
  handed to the detectors is therefore clamped to <= ``tile`` (default 512).
- **Tile-origin phase.** The ``%8`` block grid is only valid when the crop
  origin is a multiple of 8, so every region origin is snapped down to a
  multiple of 8 and ``overlap`` defaults to a multiple of 8 as well.

Pure PIL/numpy, no Qt. Bounded memory: one cropped tile per worker at a time;
the full frame is never materialized.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from shared.analysis.tile_boxes import (
    DEFAULT_OVERLAP,
    DEFAULT_TILE,
    tile_crop_boxes,
)
from tabs.image_gallery.services.artifacts import (
    Artifact,
    Severity,
    analyze_images,
)

_RANK: dict = {
    Severity.CLEAN: 0,
    Severity.MILD: 1,
    Severity.FLAGGED: 2,
}
_RANK_INV: dict = {
    0: Severity.CLEAN,
    1: Severity.MILD,
    2: Severity.FLAGGED,
}


def _crop_source(source, box: tuple[int, int, int, int]):
    """Crop *box* from a PIL image or a ``TiledPixelStore`` (duck-typed)."""
    left, top, right, bottom = (int(v) for v in box)
    try:
        width, height = source.size
        width, height = int(width), int(height)
        left = max(0, min(left, width))
        top = max(0, min(top, height))
        right = max(left, min(right, width))
        bottom = max(top, min(bottom, height))
    except Exception:
        pass
    return source.crop((left, top, right, bottom))


def _analyze_tile(source, source_image, box: tuple[int, int, int, int]):
    tile_pil = _crop_source(source, box)
    source_tile = _crop_source(source_image, box) if source_image is not None else None
    return analyze_images(tile_pil, source_tile)


def analyze_artifacts_tiled(
    source,
    *,
    source_image=None,
    tile: int = DEFAULT_TILE,
    overlap: int = DEFAULT_OVERLAP,
    workers: int = 4,
) -> dict[Artifact, Severity]:
    """Worst-of-tiles severity per artifact, full resolution, no downscale.

    ``source`` is a full-resolution ``TiledPixelStore`` or ``PIL.Image.Image``.
    ``source_image``, when given, is the matching full-res reference and is
    cropped with the SAME box as each item tile so the anchored detectors
    cancel content bias. Returns all 7 ``Artifact`` keys; fail-closed ``clean``
    on a None/unreadable source or any error. Tiles are analyzed with the
    existing ``analyze_images`` and aggregated by severity rank
    ``clean < mild < flagged`` (max, order-independent).
    """
    clean_result: dict = {art: Severity.CLEAN for art in Artifact}
    if source is None:
        return clean_result
    try:
        width, height = source.size
        width, height = int(width), int(height)
    except Exception:
        return clean_result
    if width <= 0 or height <= 0:
        return clean_result
    try:
        boxes = tile_crop_boxes(width, height, tile=tile, overlap=overlap)
    except Exception:
        return clean_result
    if not boxes:
        return clean_result

    per_tile: list[dict] = []
    worker_count = max(1, int(workers))
    if worker_count <= 1:
        for box in boxes:
            try:
                per_tile.append(_analyze_tile(source, source_image, box))
            except Exception:
                continue
    else:
        try:
            with ThreadPoolExecutor(
                max_workers=worker_count, thread_name_prefix="artifact-tile"
            ) as pool:
                futures = [
                    pool.submit(_analyze_tile, source, source_image, box)
                    for box in boxes
                ]
                for future in as_completed(futures):
                    try:
                        per_tile.append(future.result())
                    except Exception:
                        continue
        except Exception:
            # Executor setup failed — the serial path still yields a result.
            per_tile = []
            for box in boxes:
                try:
                    per_tile.append(_analyze_tile(source, source_image, box))
                except Exception:
                    continue

    result = dict(clean_result)
    best = {art: 0 for art in Artifact}
    for mapping in per_tile:
        if not mapping:
            continue
        for art in Artifact:
            rank = _RANK.get(mapping.get(art), 0)
            if rank > best[art]:
                best[art] = rank
                result[art] = _RANK_INV[rank]
    return result
