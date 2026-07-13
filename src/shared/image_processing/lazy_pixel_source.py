from __future__ import annotations

import logging
import os
import tempfile

import numpy as np
from PIL import Image

logger = logging.getLogger("ImproveImgSLI")

_spill_dir_cache: str | None = None


def _resolve_spill_dir() -> str | None:
    """Picks a real disk-backed directory for the memmap spill file.

    ``tempfile``'s default directory (``$TMPDIR``/``/tmp``) is commonly
    tmpfs (RAM-backed) on modern Linux distros -- writing the spill file
    there would just duplicate the image into a second RAM-resident
    buffer, defeating the entire point of spilling. The app's Qt cache
    location is on the same disk as the user's home directory instead.
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
            spill_dir = os.path.join(cache_dir, "large_image_spill")
            os.makedirs(spill_dir, exist_ok=True)
            _spill_dir_cache = spill_dir
            return spill_dir
    except Exception as exc:
        logger.debug("Failed to resolve Qt cache location for spill dir: %s", exc)
    return None

class LazyPixelSource:
    """Disk-backed (memmap) stand-in for a fully-decoded RGBA8 PIL image.

    docs/dev/rendering/tile-rendering-system.md Phase 3: for images past
    ``AppConstants.PHASE3_LAZY_THRESHOLD_PX``, the decoded pixel buffer is
    spilled to a memory-mapped temp file instead of staying resident as an
    anonymous-heap PIL Image for the document's lifetime -- mmap'd pages are
    backed by a file and reclaimable by the OS under memory pressure, unlike
    a Python-owned bytes buffer that must go to swap.

    Duck-types the subset of PIL.Image's interface this codebase actually
    reads off ``document.full_res_image1/2`` (``.size``, ``.width``,
    ``.height``, ``.mode``, ``.info``, ``.crop()``) so existing consumers
    need minimal branching -- see call sites gated on
    ``isinstance(x, LazyPixelSource)``.
    """

    mode = "RGBA"

    def __init__(self, memmap: np.memmap, path: str):
        self._memmap = memmap
        self._path = path
        self.info: dict = {}

    @classmethod
    def from_pil(cls, pil_image: Image.Image, tmp_dir: str | None = None) -> "LazyPixelSource":
        rgba = pil_image if pil_image.mode == "RGBA" else pil_image.convert("RGBA")
        width, height = rgba.size
        fd, path = tempfile.mkstemp(
            prefix="imgsli_lazy_",
            suffix=".raw",
            dir=tmp_dir if tmp_dir is not None else _resolve_spill_dir(),
        )
        try:
            memmap = np.memmap(
                path, dtype=np.uint8, mode="r+", shape=(height, width, 4)
            )
            memmap[:] = np.asarray(rgba, dtype=np.uint8).reshape(height, width, 4)
            memmap.flush()
        finally:
            os.close(fd)
        memmap = np.memmap(path, dtype=np.uint8, mode="r", shape=(height, width, 4))
        return cls(memmap, path)

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

    def crop(self, box: tuple[int, int, int, int]) -> Image.Image:
        left, top, right, bottom = box
        region = np.array(self._memmap[top:bottom, left:right, :], copy=True)
        return Image.fromarray(region, mode="RGBA")

    def to_pil(self) -> Image.Image:
        # Explicit copy (not a zero-copy view over the memmap): callers may
        # keep this PIL Image around after this LazyPixelSource is closed
        # (e.g. a background diff worker), so it must not depend on the
        # memmap's lifetime.
        return Image.fromarray(np.array(self._memmap), mode="RGBA")

    def close(self) -> None:
        path = self._path
        self._memmap = None
        self._path = None
        if path:
            try:
                os.remove(path)
            except OSError as exc:
                logger.debug("Failed to remove lazy pixel source temp file %s: %s", path, exc)

    def __del__(self):
        if getattr(self, "_path", None):
            self.close()

def maybe_wrap_for_lazy_storage(pil_image: Image.Image | None):
    """Wrap ``pil_image`` in a :class:`LazyPixelSource` when it's past
    ``AppConstants.PHASE3_LAZY_THRESHOLD_PX`` on either side; otherwise
    return it unchanged. Ordinary-sized images are completely unaffected."""
    if pil_image is None:
        return pil_image
    from core.constants import AppConstants

    threshold = AppConstants.PHASE3_LAZY_THRESHOLD_PX
    width, height = pil_image.size
    if max(width, height) <= threshold:
        return pil_image
    try:
        return LazyPixelSource.from_pil(pil_image)
    except OSError as exc:
        logger.warning(
            "Failed to spill large image (%dx%d) to disk, keeping it resident: %s",
            width,
            height,
            exc,
        )
        return pil_image

def close_if_lazy(image) -> None:
    """Release the temp file backing ``image`` if it's a LazyPixelSource;
    no-op for plain PIL images or ``None``."""
    if isinstance(image, LazyPixelSource):
        image.close()

def to_real_pil_copy(image: Image.Image | "LazyPixelSource") -> Image.Image:
    """Returns an independent, real PIL Image copy of ``image``, regardless
    of whether it's a plain PIL Image or a LazyPixelSource (which doesn't
    implement PIL's ``.copy()``). Used by call sites that hand images off
    to a background worker and need a copy that outlives the source."""
    if isinstance(image, LazyPixelSource):
        return image.to_pil()
    return image.copy()
