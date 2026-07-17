"""GEGL-style tiled pixel storage — always memmap-backed RGBA8.

Every decoded full-resolution image lives in a disk-backed memory map,
addressable by fixed-size host tiles (``AppConstants.PIXEL_TILE_SIZE``).
There is no small-image fast path at the public API level; callers use
``TiledPixelStore`` uniformly for all canvas tabs.

Full-res spill uses strip writes so peak RAM is one decode buffer plus a
strip, not a second full ``HxWx4`` copy beside PIL.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

if TYPE_CHECKING:
    from PySide6.QtGui import QImage

logger = logging.getLogger("ImproveImgSLI")

_spill_dir_cache: str | None = None
_AUTO_CROP_PROBE_MAX = 1024


def resolve_pixel_spill_dir() -> str | None:
    """Disk-backed directory for memmap spill files (not tmpfs)."""
    global _spill_dir_cache
    if _spill_dir_cache is not None:
        return _spill_dir_cache
    try:
        from PySide6.QtCore import QStandardPaths

        cache_dir = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.CacheLocation
        )
        if cache_dir:
            spill_dir = os.path.join(cache_dir, "pixel_tile_store")
            os.makedirs(spill_dir, exist_ok=True)
            _spill_dir_cache = spill_dir
            return spill_dir
    except Exception as exc:
        logger.debug("Failed to resolve Qt cache location for spill dir: %s", exc)
    return None


def _spill_dir(tmp_dir: str | None) -> str | None:
    return tmp_dir if tmp_dir is not None else resolve_pixel_spill_dir()


def _allocate_spill_memmap(
    width: int, height: int, tmp_dir: str | None = None
) -> tuple[np.memmap, str]:
    """Create an empty RGBA8 spill file and return a writable memmap + path."""
    width, height = max(1, int(width)), max(1, int(height))
    fd, path = tempfile.mkstemp(
        prefix="imgsli_tps_",
        suffix=".raw",
        dir=_spill_dir(tmp_dir),
    )
    try:
        memmap = np.memmap(path, dtype=np.uint8, mode="r+", shape=(height, width, 4))
        memmap[:] = 0
        memmap.flush()
    finally:
        os.close(fd)
    memmap = np.memmap(path, dtype=np.uint8, mode="r+", shape=(height, width, 4))
    return memmap, path


def _reopen_readonly(path: str, height: int, width: int) -> np.memmap:
    return np.memmap(path, dtype=np.uint8, mode="r", shape=(height, width, 4))


def _strip_height() -> int:
    from core.constants import AppConstants

    return max(1, int(AppConstants.PIXEL_TILE_SIZE))


def _write_rgba_strips(
    memmap: np.memmap,
    source: Image.Image | np.ndarray,
    *,
    src_box: tuple[int, int, int, int] | None = None,
) -> None:
    """Copy ``source`` into ``memmap`` in horizontal strips (no full ``asarray``).

    ``src_box`` is ``(left, top, right, bottom)`` in source pixel space. When
    set, only that region is written and must match ``memmap`` shape.
    """
    strip_h = _strip_height()
    out_h, out_w, _ = memmap.shape

    if isinstance(source, np.ndarray):
        arr = np.asarray(source)
        if arr.ndim != 3 or arr.shape[2] < 3:
            raise ValueError(f"Expected HxWxC array, got shape {arr.shape}")
        src_h, src_w = int(arr.shape[0]), int(arr.shape[1])
        if src_box is None:
            left, top, right, bottom = 0, 0, src_w, src_h
        else:
            left, top, right, bottom = (int(v) for v in src_box)
        if (bottom - top, right - left) != (out_h, out_w):
            raise ValueError(
                f"src_box {(right - left)}x{(bottom - top)} != memmap {out_w}x{out_h}"
            )
        y = 0
        while y < out_h:
            chunk = min(strip_h, out_h - y)
            src_y0 = top + y
            src_y1 = src_y0 + chunk
            band = arr[src_y0:src_y1, left:right, :4]
            if band.shape[2] == 3:
                rgba = np.empty((chunk, out_w, 4), dtype=np.uint8)
                rgba[:, :, :3] = band
                rgba[:, :, 3] = 255
                memmap[y : y + chunk, :, :] = rgba
            else:
                memmap[y : y + chunk, :, :] = np.asarray(band, dtype=np.uint8)
            y += chunk
        memmap.flush()
        return

    rgba = source if source.mode == "RGBA" else source.convert("RGBA")
    src_w, src_h = rgba.size
    if src_box is None:
        left, top, right, bottom = 0, 0, src_w, src_h
    else:
        left, top, right, bottom = (int(v) for v in src_box)
    if (bottom - top, right - left) != (out_h, out_w):
        raise ValueError(
            f"src_box {(right - left)}x{(bottom - top)} != memmap {out_w}x{out_h}"
        )
    y = 0
    while y < out_h:
        chunk = min(strip_h, out_h - y)
        src_y0 = top + y
        src_y1 = src_y0 + chunk
        band = rgba.crop((left, src_y0, right, src_y1))
        memmap[y : y + chunk, :, :] = np.asarray(band, dtype=np.uint8).reshape(
            chunk, out_w, 4
        )
        y += chunk
    memmap.flush()


def _auto_crop_box_scaled(
    rgba: Image.Image, *, threshold: int = 15
) -> tuple[int, int, int, int] | None:
    """BBox via bounded downscale — avoids full-res crop analysis resident."""
    from shared.image_processing.resize import get_auto_crop_box

    w, h = rgba.size
    longest = max(w, h)
    if longest <= _AUTO_CROP_PROBE_MAX:
        return get_auto_crop_box(rgba, threshold)

    scale = _AUTO_CROP_PROBE_MAX / float(longest)
    probe_w = max(1, int(round(w * scale)))
    probe_h = max(1, int(round(h * scale)))
    probe = rgba.resize((probe_w, probe_h), Image.Resampling.BILINEAR)
    box = get_auto_crop_box(probe, threshold)
    if box is None:
        return None
    pl, pt, pr, pb = box
    inv = 1.0 / scale
    left = max(0, int(pl * inv))
    top = max(0, int(pt * inv))
    right = min(w, max(left + 1, int(round(pr * inv))))
    bottom = min(h, max(top + 1, int(round(pb * inv))))
    if (left, top, right, bottom) == (0, 0, w, h):
        return None
    return (left, top, right, bottom)


def _auto_crop_box_from_ndarray(
    arr: np.ndarray, *, threshold: int = 15
) -> tuple[int, int, int, int] | None:
    """Same as ``_auto_crop_box_scaled`` for a HxWxC uint8 array (JXL path)."""
    src_h, src_w = int(arr.shape[0]), int(arr.shape[1])
    longest = max(src_w, src_h)
    if longest <= _AUTO_CROP_PROBE_MAX:
        channels = arr[:, :, :3] if arr.shape[2] >= 3 else arr
        rgb = Image.fromarray(np.asarray(channels, dtype=np.uint8), mode="RGB")
        return _auto_crop_box_scaled(rgb.convert("RGBA"), threshold=threshold)

    scale = _AUTO_CROP_PROBE_MAX / float(longest)
    step = max(1, int(1.0 / scale))
    small = np.asarray(arr[::step, ::step, :3], dtype=np.uint8)
    probe = Image.fromarray(small, mode="RGB").convert("RGBA")
    # Map probe coords: probe pixel ≈ step source pixels.
    from shared.image_processing.resize import get_auto_crop_box

    box = get_auto_crop_box(probe, threshold)
    if box is None:
        return None
    pl, pt, pr, pb = box
    left = max(0, int(pl * step))
    top = max(0, int(pt * step))
    right = min(src_w, max(left + 1, int(pr * step)))
    bottom = min(src_h, max(top + 1, int(pb * step)))
    if (left, top, right, bottom) == (0, 0, src_w, src_h):
        return None
    return (left, top, right, bottom)


def _decode_path_to_rgba(path: str | Path) -> Image.Image | np.ndarray:
    """Decode file to one RGBA surface (PIL or ndarray for JXL).

    Returns a single decode buffer — no extra ``.copy()``. Caller strip-spills
    then drops this object.
    """
    from shared.image_processing.progressive_loader import (
        JXL_SUPPORTED,
        _ensure_supported_dimensions,
    )

    path_str = os.fspath(path)
    if JXL_SUPPORTED and path_str.lower().endswith(".jxl"):
        import imagecodecs

        decoded = imagecodecs.imread(path_str)
        height, width = int(decoded.shape[0]), int(decoded.shape[1])
        _ensure_supported_dimensions(width, height, path_str)
        return decoded

    img = Image.open(path_str)
    try:
        _ensure_supported_dimensions(img.width, img.height, path_str)
        rgba = img.convert("RGBA")
        rgba.load()
        return rgba
    finally:
        img.close()


class TiledPixelStore:
    """Disk-backed RGBA8 buffer with tile-addressable reads."""

    mode = "RGBA"

    def __init__(
        self,
        memmap: np.memmap,
        path: str,
        *,
        tile_size: int,
        generation: int = 0,
    ):
        self._memmap = memmap
        self._path = path
        self._tile_size = max(1, int(tile_size))
        self._generation = int(generation)
        self.info: dict = {}
        height, width, _ = memmap.shape
        self._tile_rows = (height + self._tile_size - 1) // self._tile_size
        self._tile_cols = (width + self._tile_size - 1) // self._tile_size

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def is_open(self) -> bool:
        return self._memmap is not None

    def lease(self):
        from shared.image_processing.store_lease import StoreLease

        return StoreLease.capture(self)

    @classmethod
    def allocate(cls, width: int, height: int, tmp_dir: str | None = None) -> "TiledPixelStore":
        from core.constants import AppConstants

        memmap, path = _allocate_spill_memmap(width, height, tmp_dir)
        return cls(memmap, path, tile_size=AppConstants.PIXEL_TILE_SIZE)

    def write_pil(self, box: tuple[int, int, int, int], pil_image: Image.Image) -> None:
        left, top, right, bottom = box
        memmap = self._ensure_open()
        rgba = pil_image if pil_image.mode == "RGBA" else pil_image.convert("RGBA")
        # Local write may be small; still avoid a needless full-image asarray.
        strip_h = _strip_height()
        out_h = bottom - top
        out_w = right - left
        y = 0
        while y < out_h:
            chunk = min(strip_h, out_h - y)
            band = rgba.crop((0, y, out_w, y + chunk))
            memmap[top + y : top + y + chunk, left:right, :] = np.asarray(
                band, dtype=np.uint8
            ).reshape(chunk, out_w, 4)
            y += chunk
        memmap.flush()

    @classmethod
    def from_pil(cls, pil_image: Image.Image, tmp_dir: str | None = None) -> "TiledPixelStore":
        from core.constants import AppConstants

        rgba = pil_image if pil_image.mode == "RGBA" else pil_image.convert("RGBA")
        width, height = rgba.size
        memmap, path = _allocate_spill_memmap(width, height, tmp_dir)
        try:
            _write_rgba_strips(memmap, rgba)
        except Exception:
            try:
                os.remove(path)
            except OSError:
                pass
            raise
        memmap = _reopen_readonly(path, height, width)
        return cls(memmap, path, tile_size=AppConstants.PIXEL_TILE_SIZE)

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        tmp_dir: str | None = None,
        *,
        auto_crop: bool = False,
    ) -> "TiledPixelStore":
        from core.constants import AppConstants
        from shared.image_processing.progressive_loader import ImageSizeLimitError

        try:
            decoded = _decode_path_to_rgba(path)
        except ImageSizeLimitError:
            raise

        if isinstance(decoded, np.ndarray):
            arr = np.asarray(decoded)
            src_h, src_w = int(arr.shape[0]), int(arr.shape[1])
            src_box = (
                _auto_crop_box_from_ndarray(arr) if auto_crop else None
            )
            if src_box is None:
                out_w, out_h = src_w, src_h
            else:
                left, top, right, bottom = src_box
                out_w, out_h = right - left, bottom - top
                logger.info(
                    "Auto-crop applied: %s (Orig: %dx%d)", src_box, src_w, src_h
                )
            memmap, spill_path = _allocate_spill_memmap(out_w, out_h, tmp_dir)
            try:
                _write_rgba_strips(memmap, arr, src_box=src_box)
            except Exception:
                try:
                    os.remove(spill_path)
                except OSError:
                    pass
                raise
            del arr
            del decoded
            memmap = _reopen_readonly(spill_path, out_h, out_w)
            return cls(memmap, spill_path, tile_size=AppConstants.PIXEL_TILE_SIZE)

        rgba = decoded if decoded.mode == "RGBA" else decoded.convert("RGBA")
        src_box = _auto_crop_box_scaled(rgba) if auto_crop else None
        if src_box is None:
            out_w, out_h = rgba.size
        else:
            left, top, right, bottom = src_box
            out_w, out_h = right - left, bottom - top
            logger.info("Auto-crop applied: %s (Orig: %s)", src_box, rgba.size)

        memmap, spill_path = _allocate_spill_memmap(out_w, out_h, tmp_dir)
        try:
            _write_rgba_strips(memmap, rgba, src_box=src_box)
        except Exception:
            try:
                os.remove(spill_path)
            except OSError:
                pass
            raise
        del rgba
        memmap = _reopen_readonly(spill_path, out_h, out_w)
        return cls(memmap, spill_path, tile_size=AppConstants.PIXEL_TILE_SIZE)

    @property
    def tile_size(self) -> int:
        return self._tile_size

    @property
    def tile_rows(self) -> int:
        return self._tile_rows

    @property
    def tile_cols(self) -> int:
        return self._tile_cols

    @property
    def size(self) -> tuple[int, int]:
        height, width, _ = self._memmap.shape
        return (width, height)

    @property
    def width(self) -> int:
        return self._memmap.shape[1]

    @property
    def height(self) -> int:
        return self._memmap.shape[0]

    def _ensure_open(self) -> np.memmap:
        if self._memmap is None:
            raise RuntimeError("TiledPixelStore is closed")
        return self._memmap

    def read_tile(self, row: int, col: int) -> Image.Image:
        """Return one host tile as a PIL RGBA image."""
        memmap = self._ensure_open()
        if row < 0 or col < 0 or row >= self._tile_rows or col >= self._tile_cols:
            raise IndexError(f"tile ({row}, {col}) out of range")
        ts = self._tile_size
        top = row * ts
        left = col * ts
        bottom = min(top + ts, self.height)
        right = min(left + ts, self.width)
        region = np.array(memmap[top:bottom, left:right, :], copy=True)
        return Image.fromarray(region, mode="RGBA")

    def crop(self, box: tuple[int, int, int, int]) -> Image.Image:
        left, top, right, bottom = box
        memmap = self._ensure_open()
        region = np.array(memmap[top:bottom, left:right, :], copy=True)
        return Image.fromarray(region, mode="RGBA")

    def crop_apron_rect(
        self, left: int, top: int, right: int, bottom: int, apron: int = 1
    ) -> Image.Image:
        """Crop ``(left, top, right, bottom)`` expanded by ``apron`` pixels."""
        w, h = self.size
        al = max(0, left - apron)
        at = max(0, top - apron)
        ar = min(w, right + apron)
        ab = min(h, bottom + apron)
        return self.crop((al, at, ar, ab))

    def materialize_full(self) -> Image.Image:
        """Return a full in-memory RGBA copy.

        Prefer :meth:`crop`, :meth:`read_tile`, or tile iteration for
        residency/export paths. This materializes every pixel and can spike
        CPU/RAM on first use — acceptable only for workers that inherently
        need the whole image (SSIM/unify/export resize).
        """
        memmap = self._ensure_open()
        return Image.fromarray(np.array(memmap), mode="RGBA")

    def to_pil(self) -> Image.Image:
        return self.materialize_full()

    def close(self) -> None:
        path = self._path
        self._memmap = None
        self._path = None
        self._generation += 1
        if path:
            try:
                os.remove(path)
            except OSError as exc:
                logger.debug("Failed to remove TiledPixelStore temp file %s: %s", path, exc)

    def __enter__(self) -> "TiledPixelStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self):
        if getattr(self, "_path", None):
            self.close()


def qimage_from_pixel_source(source, box: tuple[int, int, int, int] | None = None) -> "QImage":
    """Convert PIL or TiledPixelStore region to QImage."""
    from PySide6.QtGui import QImage

    if isinstance(source, TiledPixelStore):
        if box is not None:
            pil = source.crop(box)
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
