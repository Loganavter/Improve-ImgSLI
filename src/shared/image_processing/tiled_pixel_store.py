"""GEGL-style tiled pixel storage — always memmap-backed RGBA8.

Every decoded full-resolution image lives in a disk-backed memory map,
addressable by fixed-size host tiles (``AppConstants.PIXEL_TILE_SIZE``).
There is no small-image fast path at the public API level; callers use
``TiledPixelStore`` uniformly for all canvas tabs.

Full-res spill uses strip writes so peak RAM is one decode buffer plus a
strip, not a second full ``HxWx4`` copy beside PIL.
Audit-Meta: pattern=state-machine reason="one memmap lifecycle — splitting threads memmap/shape/tile_size"
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

# Held for the process's whole lifetime once acquired (module-level so it
# isn't garbage-collected, which would release the OS lock early). Whether
# *this* process is the sole live holder of the spill dir -- see
# resolve_pixel_spill_dir's docstring for why this replaced a hand-rolled
# PID-sentinel-plus-/proc scheme.
_instance_lock = None
_have_exclusive_lock = False


def resolve_pixel_spill_dir() -> str | None:
    """Disk-backed directory for memmap spill files (not tmpfs).

    Also acquires an exclusive, cross-platform ``QLockFile`` on the
    directory for the rest of this process's life, recording the result in
    ``_have_exclusive_lock`` for :func:`purge_stale_spill_files` to read.

    This used to be a hand-written PID-sentinel file checked against
    ``/proc`` to decide whether a leftover lock belonged to a dead process
    -- ``/proc`` only exists on Linux, so the same scheme ported naively to
    the Windows/macOS builds this project also ships would need a second,
    platform-specific liveness check. ``QLockFile`` already solves exactly
    this (stale-lock detection via PID+hostname, or a time-based fallback
    when that isn't possible) with one implementation Qt maintains per
    platform, so there is nothing OS-specific left here at all.
    """
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
            _acquire_instance_lock(spill_dir)
            return spill_dir
    except Exception as exc:
        logger.debug("Failed to resolve Qt cache location for spill dir: %s", exc)
    return None


def _acquire_instance_lock(spill_dir: str) -> None:
    """Split out of :func:`resolve_pixel_spill_dir` so tests can drive the
    lock-acquisition step directly against a temp directory without also
    needing to fake ``QStandardPaths``'s real cache location.

    Non-blocking: a live sibling instance must not stall our startup.
    ``QLockFile.tryLock`` itself detects and removes a stale lock left by a
    dead process (crash, force-kill) before granting it to us, so a
    leftover lock file is never a permanent blocker the way the old
    PID-sentinel scheme could become if its dead-PID sweep never got to run
    (see ``bootstrap.py``'s ``_purge_stale_pixel_spill`` docstring for that
    race)."""
    global _instance_lock, _have_exclusive_lock
    from PySide6.QtCore import QLockFile

    lock = QLockFile(os.path.join(spill_dir, ".instance.lock"))
    _have_exclusive_lock = lock.tryLock(0)
    _instance_lock = lock  # keep alive regardless of outcome


def purge_stale_spill_files() -> int:
    """Delete leftover ``imgsli_tps_*.raw`` files from crashed/killed sessions.

    Safe to call at startup before any :class:`TiledPixelStore` is allocated
    for this process (:func:`resolve_pixel_spill_dir` must have been called
    first -- it decides, via the exclusive lock, whether purging is safe).

    Only purges when this process holds the exclusive spill-dir lock, i.e.
    no other ImgSLI instance is currently live: with the lock held, every
    ``imgsli_tps_*.raw`` file found is guaranteed to be either ours (none
    yet, since this runs before any store is allocated) or an orphan from a
    session that's provably no longer running. Returns the number of bytes
    reclaimed.
    """
    spill_dir = resolve_pixel_spill_dir()
    if not spill_dir:
        return 0

    if not _have_exclusive_lock:
        logger.debug(
            "[SpillPurge] Another live ImgSLI instance holds the spill dir lock, skipping purge."
        )
        return 0

    reclaimed = 0
    try:
        for name in os.listdir(spill_dir):
            if not (name.startswith("imgsli_tps_") and name.endswith(".raw")):
                continue
            full = os.path.join(spill_dir, name)
            try:
                size = os.path.getsize(full)
                os.remove(full)
                reclaimed += size
                logger.debug("[SpillPurge] Removed stale spill file %s (%d bytes)", name, size)
            except OSError as exc:
                logger.debug("[SpillPurge] Could not remove %s: %s", name, exc)
    except OSError:
        pass

    if reclaimed:
        logger.info("[SpillPurge] Reclaimed %.1f MiB from stale pixel spill files.", reclaimed / 1024 / 1024)
    return reclaimed


def _spill_dir(tmp_dir: str | None) -> str | None:
    return tmp_dir if tmp_dir is not None else resolve_pixel_spill_dir()


def _allocate_spill_memmap(
    width: int, height: int, tmp_dir: str | None = None
) -> tuple[np.memmap, str]:
    """Create an empty RGBA8 spill file and return a writable memmap + path."""
    width, height = max(1, int(width)), max(1, int(height))
    expected_size = width * height * 4
    fd, path = tempfile.mkstemp(
        prefix="imgsli_tps_",
        suffix=".raw",
        dir=_spill_dir(tmp_dir),
    )
    
    try:
        try:
            if hasattr(os, 'posix_fallocate'):
                try:
                    os.posix_fallocate(fd, 0, expected_size)
                except OSError as exc:
                    raise OSError(f"No space to allocate {expected_size} bytes for pixel store: {exc}") from exc
            else:
                os.ftruncate(fd, expected_size)
        finally:
            os.close(fd)
            
        memmap = np.memmap(path, dtype=np.uint8, mode="r+", shape=(height, width, 4))
        memmap[:] = 0
        memmap.flush()
        return memmap, path
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        raise


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
        import time

        # Helper: normalize uint16 -> uint8 by scaling (>>8), not truncation
        def _to_u8(b: np.ndarray) -> np.ndarray:
            if b.dtype == np.uint8:
                return b
            if b.dtype == np.uint16:
                # 16-bit JXL etc: 0..65535 -> 0..255 via high byte (>>8), i.e.
                # 300 -> 1 not 44 (mod-256 truncation). Equivalent to //257.
                return (b >> 8).astype(np.uint8)
            # Fallback for float or other: clip and cast
            if b.dtype.kind == "f":
                return np.clip(b, 0, 255).astype(np.uint8)
            return np.asarray(b, dtype=np.uint8)

        y = 0
        while y < out_h:
            chunk = min(strip_h, out_h - y)
            src_y0 = top + y
            src_y1 = src_y0 + chunk
            band = arr[src_y0:src_y1, left:right, :4]
            if band.shape[2] == 3:
                rgba = np.empty((chunk, out_w, 4), dtype=np.uint8)
                rgba[:, :, :3] = _to_u8(band)
                rgba[:, :, 3] = 255
                memmap[y : y + chunk, :, :] = rgba
            else:
                memmap[y : y + chunk, :, :] = _to_u8(band)
            y += chunk
            time.sleep(0.001)
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
    import time
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
        time.sleep(0.001)
    memmap.flush()


def _find_trim_box_vips(
    rgb: np.ndarray, *, threshold: int = 15
) -> tuple[int, int, int, int] | None:
    """BBox of non-black content via vips ``find_trim`` — no PIL passes.

    ``rgb`` must already be the (possibly downscaled) probe buffer; this
    only wraps it into a vips image (single memcpy, no per-pixel Python).
    Returns ``None`` on failure so callers can fall back to the PIL path.
    """
    from shared.image_processing.progressive_loader import PYVIPS_SUPPORTED

    if not PYVIPS_SUPPORTED:
        return None
    try:
        import pyvips  # type: ignore[import-untyped]  # pyvips has no stubs

        a = np.ascontiguousarray(rgb[:, :, :3], dtype=np.uint8)
        h, w = a.shape[0], a.shape[1]
        vimg = pyvips.Image.new_from_memory(a.tobytes(), w, h, 3, "uchar")
        left, top, width, height = vimg.find_trim(
            threshold=threshold, background=[0, 0, 0]
        )
        if width <= 0 or height <= 0:
            return None
        right, bottom = left + width, top + height
        if (left, top, right, bottom) == (0, 0, w, h):
            return None
        return (left, top, right, bottom)
    except Exception as e:
        logger.debug("vips find_trim probe failed: %s", e)
        return None


def _auto_crop_box_scaled(
    rgba: Image.Image, *, threshold: int = 15
) -> tuple[int, int, int, int] | None:
    """BBox via bounded downscale — avoids full-res crop analysis resident."""
    from shared.image_processing.resize import get_auto_crop_box

    w, h = rgba.size
    longest = max(w, h)
    if longest <= _AUTO_CROP_PROBE_MAX:
        vips_box = _find_trim_box_vips(np.asarray(rgba), threshold=threshold)
        if vips_box is not None:
            return vips_box
        return get_auto_crop_box(rgba, threshold)

    scale = _AUTO_CROP_PROBE_MAX / float(longest)
    probe_w = max(1, int(round(w * scale)))
    probe_h = max(1, int(round(h * scale)))
    # NEAREST: BILINEAR on RGBA makes PIL premultiply-convert the whole
    # full-res image (RGBA->RGBa), a multi-GB copy for 20k+ sources. For a
    # bbox probe nearest sampling is sufficient.
    probe = rgba.resize((probe_w, probe_h), Image.Resampling.NEAREST)
    inv = 1.0 / scale

    vips_box = _find_trim_box_vips(np.asarray(probe), threshold=threshold)
    if vips_box is not None:
        pl, pt, pr, pb = vips_box
    else:
        box = get_auto_crop_box(probe, threshold)
        if box is None:
            return None
        pl, pt, pr, pb = box

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
        vips_box = _find_trim_box_vips(arr, threshold=threshold)
        if vips_box is not None:
            return vips_box
        channels = arr[:, :, :3] if arr.shape[2] >= 3 else arr
        rgb = Image.fromarray(np.asarray(channels, dtype=np.uint8), mode="RGB")
        return _auto_crop_box_scaled(rgb.convert("RGBA"), threshold=threshold)

    scale = _AUTO_CROP_PROBE_MAX / float(longest)
    step = max(1, int(1.0 / scale))
    small = np.asarray(arr[::step, ::step, :3], dtype=np.uint8)

    vips_box = _find_trim_box_vips(small, threshold=threshold)
    if vips_box is None:
        probe = Image.fromarray(small, mode="RGB").convert("RGBA")
        from shared.image_processing.resize import get_auto_crop_box

        box = get_auto_crop_box(probe, threshold)
        if box is None:
            return None
        vips_box = box

    pl, pt, pr, pb = vips_box
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


def _stream_pyvips_to_memmap(path_str: str, tmp_dir: str | None, auto_crop: bool = False) -> tuple[np.memmap, str, int, int]:
    import pyvips

    img = pyvips.Image.new_from_file(path_str, access="sequential")
    if not img.hasalpha():
        img = img.bandjoin(255)
    if img.format != "uchar":
        if img.format == "ushort":
            # 16-bit -> 8-bit by scaling, not C truncation (cast("uchar") keeps low byte)
            img = (img / 257).cast("uchar")
        elif img.format in ("char", "short", "int"):
            # Signed or other integer: clamp then cast
            img = img.cast("uchar")
        elif img.format in ("float", "double"):
            img = (img * 255).cast("uchar")
        else:
            img = img.cast("uchar")

    src_w = img.width
    src_h = img.height

    src_box = None
    if auto_crop:
        try:
            probe_img = pyvips.Image.thumbnail(path_str, _AUTO_CROP_PROBE_MAX)
            probe_rgb = probe_img[:3] if probe_img.bands >= 3 else probe_img
            left, top, width, height = probe_rgb.find_trim(
                threshold=15, background=[0, 0, 0]
            )
            if width > 0 and height > 0 and not (
                left == 0 and top == 0
                and width == probe_img.width and height == probe_img.height
            ):
                right, bottom = left + width, top + height
                scale_w = src_w / probe_img.width
                scale_h = src_h / probe_img.height
                l2 = max(0, int(left * scale_w))
                t2 = max(0, int(top * scale_h))
                r2 = min(src_w, max(l2 + 1, int(round(right * scale_w))))
                b2 = min(src_h, max(t2 + 1, int(round(bottom * scale_h))))
                if (l2, t2, r2, b2) != (0, 0, src_w, src_h):
                    src_box = (l2, t2, r2, b2)
        except Exception as e:
            logger.debug("pyvips auto-crop probe failed: %s", e)

    out_w = src_w
    out_h = src_h
    if src_box is not None:
        left, top, right, bottom = src_box
        out_w = right - left
        out_h = bottom - top
        logger.info("Auto-crop applied via pyvips: %s (Orig: %dx%d)", src_box, src_w, src_h)

    memmap, spill_path = _allocate_spill_memmap(out_w, out_h, tmp_dir)

    try:
        import time
        strip_h = _strip_height()
        if src_box is not None:
            left, top, right, bottom = src_box
            img = img.crop(left, top, out_w, out_h)

        # Region.fetch (not repeated top-level crop().write_to_memory() calls)
        # is required here: each independent sink evaluation on a
        # sequential-access source restarts the reader's line cursor, so a
        # second strip pull past what the first already consumed raises
        # "out of order read". Region.fetch shares one cursor across calls.
        region = pyvips.Region.new(img)
        y = 0
        while y < out_h:
            chunk = min(strip_h, out_h - y)
            strip_bytes = region.fetch(0, y, out_w, chunk)
            arr = np.ndarray(buffer=strip_bytes, dtype=np.uint8, shape=(chunk, out_w, 4))
            memmap[y:y+chunk, :, :] = arr
            y += chunk
            time.sleep(0.001)
        memmap.flush()
    except Exception:
        try:
            os.remove(spill_path)
        except OSError:
            pass
        raise

    return memmap, spill_path, out_w, out_h


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
        owns_file: bool = True,
    ):
        self._memmap: np.memmap | None = memmap
        self._path: str | None = path
        self._owns_file: bool = bool(owns_file)
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
        import time
        y = 0
        while y < out_h:
            chunk = min(strip_h, out_h - y)
            band = rgba.crop((0, y, out_w, y + chunk))
            memmap[top + y : top + y + chunk, left:right, :] = np.asarray(
                band, dtype=np.uint8
            ).reshape(chunk, out_w, 4)
            y += chunk
            time.sleep(0.001)
        memmap.flush()

    def write_array(self, box: tuple[int, int, int, int], arr: np.ndarray) -> None:
        """Write an (H, W, 4) uint8 array into ``box`` without a PIL round-trip."""
        left, top, right, bottom = box
        memmap = self._ensure_open()
        memmap[top:bottom, left:right, :] = arr

    def read_array(self, box: tuple[int, int, int, int]) -> np.ndarray:
        """Read ``box`` as an (H, W, 4) uint8 array without a PIL round-trip."""
        left, top, right, bottom = box
        memmap = self._ensure_open()
        return np.asarray(memmap[top:bottom, left:right, :], dtype=np.uint8)

    def flush(self) -> None:
        self._ensure_open().flush()

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
        import time
        from core.constants import AppConstants
        from shared.image_processing.progressive_loader import (
            ImageSizeLimitError,
            pyvips_can_stream,
        )

        t0 = time.perf_counter()
        path_str = os.fspath(path)
        logger.info(f"[TileStore] from_path starting for {path_str} (auto_crop={auto_crop})")
        if pyvips_can_stream(path_str):
            try:
                memmap, spill_path, out_w, out_h = _stream_pyvips_to_memmap(path_str, tmp_dir, auto_crop=auto_crop)
                memmap = _reopen_readonly(spill_path, out_h, out_w)
                elapsed = time.perf_counter() - t0
                logger.info(f"[TileStore] pyvips streamed {path_str} ({out_w}x{out_h}) in {elapsed:.3f}s")
                return cls(memmap, spill_path, tile_size=AppConstants.PIXEL_TILE_SIZE)
            except Exception as e:
                logger.warning("pyvips stream decode failed for %s, falling back to PIL/imagecodecs: %s", path_str, e)

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

    @classmethod
    def from_embedded_cache(cls, cache_path: str, width: int, height: int) -> "TiledPixelStore":
        """Wrap an already-decoded RGBA8 raw buffer extracted from a project cache.

        The buffer's dimensions already reflect whatever crop was applied
        when it was captured at save time — no auto-crop pass here.

        The store is a read-only tenant: the file is owned by the project
        extract cache (pixel_cache_registry), so :meth:`close` must not
        delete it.
        """
        from core.constants import AppConstants

        memmap = _reopen_readonly(cache_path, height, width)
        return cls(memmap, cache_path, tile_size=AppConstants.PIXEL_TILE_SIZE, owns_file=False)

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
    def path(self) -> str | None:
        return self._path

    @property
    def size(self) -> tuple[int, int]:
        height, width, _ = self._ensure_open().shape
        return (width, height)

    @property
    def width(self) -> int:
        return self._ensure_open().shape[1]

    @property
    def height(self) -> int:
        return self._ensure_open().shape[0]

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

    def materialize_full(self) -> Image.Image:
        """Return a full in-memory RGBA copy.

        Prefer :meth:`crop`, :meth:`read_tile`, or tile iteration for
        residency/export paths. This materializes every pixel and can spike
        CPU/RAM on first use — acceptable only for workers that inherently
        need the whole image (SSIM/unify/export resize).
        """
        memmap = self._ensure_open()
        return Image.fromarray(np.array(memmap), mode="RGBA")

    def close(self) -> None:
        path = self._path
        owns = getattr(self, "_owns_file", True)
        self._memmap = None
        self._path = None
        self._generation += 1
        if path and owns:
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