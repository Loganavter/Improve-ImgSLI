"""Duck-typed pixel-source adapters: PIL / QImage / ndarray / TiledPixelStore.

Split out of :mod:`engine.store.tiled_pixel_store` (Part D, 2026-10-17 —
see docs/dev/CODE_MASS_REDUCTION.md). These helpers touch a store only
through its public API (``read_array`` / ``read_tile`` / ``tile_rows`` /
``tile_cols`` / ``tile_size`` / ``size``) and never ``_memmap``, so they carry
no part of the memmap lifecycle the store's ``Audit-Meta: pattern=state-machine``
covers. ``tiled_pixel_store`` re-exports all five names for existing importers.
"""

from __future__ import annotations

import logging

import numpy as np
from PIL import Image

from engine.store.tiled_pixel_store import TiledPixelStore
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


def qimage_from_pixel_source(source, box: tuple[int, int, int, int] | None = None) -> "QImage":
    """Convert PIL, TiledPixelStore, or QImage region to QImage.

    QImage sources show up here for progressive-preview slots (multi_compare
    keeps the decoded preview as a QImage, not PIL -- see
    ``slot_pixel_sources``); QImage has neither PIL's ``.crop()``/``.mode``
    nor TiledPixelStore's ``.size`` tuple, so it needs its own branch instead
    of falling into the PIL-shaped ``else`` below.
    """
    from PySide6.QtGui import QImage

    if isinstance(source, QImage):
        if box is not None:
            left, top, right, bottom = box
            return source.copy(left, top, right - left, bottom - top)
        return source

    if isinstance(source, np.ndarray):
        arr = np.ascontiguousarray(source)
        if arr.ndim != 3 or arr.shape[2] < 4:
            rgba = np.empty((arr.shape[0], arr.shape[1], 4), dtype=np.uint8)
            rgba[:, :, :3] = arr[:, :, :3] if arr.ndim == 3 and arr.shape[2] >= 3 else arr
            rgba[:, :, 3] = 255
            arr = rgba
        if box is not None:
            left, top, right, bottom = box
            arr = np.ascontiguousarray(arr[top:bottom, left:right])
        height, width, _ = arr.shape
        return QImage(
            arr.data,
            width,
            height,
            width * 4,
            QImage.Format.Format_RGBA8888,
        ).copy()

    if isinstance(source, TiledPixelStore):
        if box is not None:
            # Bypass the PIL round-trip (fromarray -> convert -> tobytes),
            # which is 2-3 redundant full-tile copies on top of the memmap
            # read: read_array is a numpy *view* (no copy), so the only real
            # copy left is the contiguity fix-up below, plus QImage's own
            # detach copy. Hot path for realize_tile_plan's per-frame
            # hi-res tile crops (multi-GB/frame on a 20000px source).
            left, top, right, bottom = box
            arr = np.ascontiguousarray(source.read_array(box))
            width, height = right - left, bottom - top
            return QImage(
                arr.data,
                width,
                height,
                width * 4,
                QImage.Format.Format_RGBA8888,
            ).copy()
        else:
            width, height = source.size
            pil = Image.new("RGBA", (width, height))
            for row in range(source.tile_rows):
                for col in range(source.tile_cols):
                    tile = source.read_tile(row, col)
                    top = row * source.tile_size
                    left = col * source.tile_size
                    pil.paste(tile, (left, top))
    else:
        pil = source.crop(box) if box is not None else source
        if pil.mode != "RGBA":
            pil = pil.convert("RGBA")
    return QImage(
        pil.tobytes("raw", "RGBA"),
        pil.width,
        pil.height,
        pil.width * 4,
        QImage.Format.Format_RGBA8888,
    ).copy()


def pixel_source_size(source) -> tuple[int, int]:
    """``(width, height)`` for any renderer pixel source: ``TiledPixelStore``
    exposes it as a tuple property, ``QImage`` as a method pair, numpy arrays
    as ``(H, W, C)`` shape, and PIL images / Qt ``QSize``-returning objects
    through their ``size`` — callers that accept any of these (e.g.
    progressive-preview upload paths) go through this instead of hardcoding
    one shape."""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QImage

    try:
        if source is None:
            return (0, 0)
        if isinstance(source, QImage):
            return source.width(), source.height()
        if isinstance(source, np.ndarray):
            return int(source.shape[1]), int(source.shape[0])
        width = getattr(source, "width", None)
        height = getattr(source, "height", None)
        if width is not None and height is not None:
            w = width() if callable(width) else width
            h = height() if callable(height) else height
            return int(w), int(h)
        size = source.size
        if callable(size):
            size = size()
        if isinstance(size, QSize):
            return int(size.width()), int(size.height())
        if size is None:
            return (0, 0)
        return (int(size[0]), int(size[1]))
    except Exception:
        # Closed TiledPixelStore (Python 3.14 hasattr only catches
        # AttributeError, so size/width raise RuntimeError) or any
        # malformed source — treat as empty rather than crash render.
        return (0, 0)


def maybe_wrap_pixel_store(pil_image: Image.Image | None):
    """Store decoded full-res pixels in a :class:`TiledPixelStore`."""
    if pil_image is None:
        return pil_image
    if isinstance(pil_image, TiledPixelStore):
        return pil_image
    try:
        return TiledPixelStore.from_pil(pil_image)
    except OSError as exc:
        logger.warning(
            "Failed to spill image (%dx%d) to TiledPixelStore, keeping PIL resident: %s",
            pil_image.width,
            pil_image.height,
            exc,
        )
        return pil_image


def close_pixel_store(image) -> None:
    if isinstance(image, TiledPixelStore):
        image.close()


def to_real_pil_copy(image: Image.Image | TiledPixelStore) -> Image.Image:
    if isinstance(image, TiledPixelStore):
        return image.materialize_full()
    return image.copy()
