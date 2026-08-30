import logging
import os
from typing import TYPE_CHECKING

from PIL import Image

from shared.image_processing.resize import crop_black_borders
from core.constants import AppConstants

if TYPE_CHECKING:
    from PySide6.QtGui import QImage

logger = logging.getLogger("ImproveImgSLI")

try:
    import imagecodecs

    JXL_SUPPORTED = True
    logger.info("JXL Support: imagecodecs detected. JXL support enabled.")
except ImportError:
    JXL_SUPPORTED = False
    logger.warning("JXL Support: imagecodecs NOT detected. JXL support disabled.")
except Exception as e:
    JXL_SUPPORTED = False
    logger.error(f"JXL Support: Error during initialization: {e}")

try:
    import pyvips  # type: ignore[import-untyped]  # pyvips has no stubs

    PYVIPS_SUPPORTED = True
    logger.info("pyvips detected. True ROI streaming enabled.")
except ImportError:
    PYVIPS_SUPPORTED = False
    logger.debug("pyvips NOT detected. True ROI streaming disabled.")
except Exception as e:
    PYVIPS_SUPPORTED = False
    logger.error(f"pyvips Support: Error during initialization: {e}")

class ImageSizeLimitError(ValueError):
    pass


def _ensure_supported_dimensions(width: int, height: int, image_path: str, ignore_limit: bool = False) -> None:
    if ignore_limit:
        return
    max_dim = int(getattr(AppConstants, "MAX_SUPPORTED_IMAGE_DIMENSION", 65536))
    if max(int(width), int(height)) > max_dim:
        raise ImageSizeLimitError(
            f"Image is too large for the installed decoder: {width}x{height} "
            f"exceeds the {max_dim}px-per-side limit. Streaming decode "
            f"(libvips) is unavailable for this file."
        )


_vips_suffixes_cache: frozenset[str] | None = None


def _vips_suffixes() -> frozenset[str]:
    """Lowercased ``pyvips.get_suffixes()`` (e.g. ``.jxl``, ``.jpg``), cached.

    ``get_suffixes()`` reflects the *installed* libvips build's loaders —
    JXL/HEIF/AVIF are optional codecs that some builds lack, so capability
    must be probed per format, not assumed from ``PYVIPS_SUPPORTED`` alone.
    """
    global _vips_suffixes_cache
    if _vips_suffixes_cache is None:
        try:
            import pyvips

            _vips_suffixes_cache = frozenset(
                s.lower() for s in pyvips.get_suffixes()
            )
        except Exception:
            _vips_suffixes_cache = frozenset()
    return _vips_suffixes_cache


def pyvips_can_stream(path: str | os.PathLike) -> bool:
    """Whether pyvips can stream-decode ``path``'s format with this libvips.

    Unlike the module-wide ``PYVIPS_SUPPORTED`` flag, this checks the
    *file's own* extension against what the installed libvips build actually
    has loaders for. The streaming path bypasses
    ``MAX_SUPPORTED_IMAGE_DIMENSION``, so probes must only skip the bound
    for files that will actually stream — not for files that will fall back
    to the PIL/imagecodecs full-frame backend (which must keep enforcing it).
    """
    if not PYVIPS_SUPPORTED:
        return False
    ext = os.path.splitext(os.fspath(path))[1].lower()
    return bool(ext) and ext in _vips_suffixes()

def should_use_progressive_load(
    file_path: str, file_size_bytes: int | None = None
) -> bool:
    if not file_path:
        return False

    if JXL_SUPPORTED and file_path.lower().endswith(".jxl"):
        return True

    if file_size_bytes is None:
        try:
            file_size_bytes = os.path.getsize(file_path)
        except OSError:
            file_size_bytes = 0
    PROGRESSIVE_SIZE_THRESHOLD = getattr(
        AppConstants, "PROGRESSIVE_LOAD_THRESHOLD_BYTES", 2 * 1024 * 1024
    )

    if file_size_bytes >= PROGRESSIVE_SIZE_THRESHOLD:
        return True

    try:

        with Image.open(file_path) as img:
            width, height = img.size
            _ensure_supported_dimensions(width, height, file_path, ignore_limit=pyvips_can_stream(file_path))
            FULL_HD_PIXELS = 1920 * 1080
            return (width * height) >= FULL_HD_PIXELS
    except ImageSizeLimitError:
        raise
    except Exception as e:

        if not file_path.lower().endswith(".jxl"):
            logger.debug(f"Failed to check image dimensions: {e}")
        return False

def load_preview_image(image_path: str, auto_crop: bool = False) -> "QImage | None":
    """Load a bounded progressive preview for display-tier use only.

    Returns ``QImage`` RGBA8888 capped at 1024 px on the long edge. Callers
    store the result in ``document.preview_image*`` — never wrap with
    ``TiledPixelStore`` (full-res tier owns memmap storage).

    When the installed libvips can stream the file's format, the preview is
    produced by ``pyvips.thumbnail`` — a real streaming thumbnail (no
    full-frame decode). This matters for large JXL/HEIF/AVIF sources, where
    the imagecodecs/QImageReader fallbacks below would otherwise materialize
    the entire frame just to build a 1024px preview.
    """
    try:
        from PySide6.QtGui import QImage, QImageReader
        from PySide6.QtCore import QSize

        if pyvips_can_stream(image_path):
            return _load_preview_vips(image_path, auto_crop=auto_crop)

        if JXL_SUPPORTED and image_path.lower().endswith(".jxl"):
            logger.info(f"Loading JXL preview for: {image_path}")
            decoded = imagecodecs.imread(image_path)
            img = Image.fromarray(decoded)

            original_width, original_height = img.size
            _ensure_supported_dimensions(original_width, original_height, image_path)
            max_preview_size = 1024
            scale = min(
                max_preview_size / original_width, max_preview_size / original_height
            )

            if scale < 1.0:
                new_width = int(original_width * scale)
                new_height = int(original_height * scale)
                img = img.resize((new_width, new_height), Image.Resampling.BILINEAR)

            preview = img.convert("RGBA")
            if auto_crop:
                preview = crop_black_borders(preview)
            
            from shared.image_processing.tiled_pixel_store import qimage_from_pixel_source
            return qimage_from_pixel_source(preview)

        reader = QImageReader(image_path)
        reader.setAllocationLimit(16384)
        if reader.format().isEmpty():
            logger.warning(f"QImageReader unsupported format for {image_path}, falling back to PIL")
            with Image.open(image_path) as img:
                original_width, original_height = img.size
                _ensure_supported_dimensions(original_width, original_height, image_path)
                max_preview_size = 1024
                scale = min(
                    max_preview_size / original_width, max_preview_size / original_height
                )

                if scale >= 1.0:
                    preview = img.copy().convert("RGBA")
                else:
                    new_width = int(original_width * scale)
                    new_height = int(original_height * scale)
                    preview = img.copy()
                    preview.thumbnail((new_width, new_height), Image.Resampling.BILINEAR)
                    preview = preview.convert("RGBA")

                if auto_crop:
                    preview = crop_black_borders(preview)
                from shared.image_processing.tiled_pixel_store import qimage_from_pixel_source
                return qimage_from_pixel_source(preview)

        size = reader.size()
        if size.isValid():
            original_width, original_height = size.width(), size.height()
            _ensure_supported_dimensions(original_width, original_height, image_path)
            max_preview_size = 1024
            scale = min(max_preview_size / original_width, max_preview_size / original_height)
            
            if scale < 1.0:
                new_width = max(1, int(original_width * scale))
                new_height = max(1, int(original_height * scale))
                reader.setScaledSize(QSize(new_width, new_height))
            
            qimg = reader.read()
            if qimg.isNull():
                logger.error(f"QImageReader returned null image for {image_path}")
                return None
            
            qimg = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
            
            if auto_crop:
                pil_probe = Image.frombytes("RGBA", (qimg.width(), qimg.height()), qimg.bits())
                from shared.image_processing.resize import get_auto_crop_box
                bbox = get_auto_crop_box(pil_probe, 15)
                if bbox is not None:
                    qimg = qimg.copy(bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1])
            
            return qimg
        else:
            return None
    except ImageSizeLimitError:
        raise
    except Exception as e:
        logger.error(f"Failed to load preview image {image_path}: {e}")
        return None


def _load_preview_vips(image_path: str, auto_crop: bool = False) -> "QImage | None":
    """Streaming preview via ``pyvips.thumbnail`` (no full-frame decode)."""
    try:
        import numpy as np
        import pyvips
        from PySide6.QtGui import QImage
        from shared.image_processing.tiled_pixel_store import (
            get_cached_crop_box,
            qimage_from_pixel_source,
        )

        thumb = pyvips.Image.thumbnail(
            image_path, 1024, height=1024, size=pyvips.enums.Size.DOWN
        )
        if not thumb.hasalpha():
            thumb = thumb.bandjoin(255)
        if thumb.format != "uchar":
            thumb = thumb.cast("uchar")
        arr = np.ndarray(
            buffer=thumb.write_to_memory(),
            dtype=np.uint8,
            shape=(thumb.height, thumb.width, thumb.bands),
        )
        if arr.shape[2] != 4:
            rgb = arr[:, :, :3] if arr.shape[2] >= 3 else arr
            arr = np.empty((thumb.height, thumb.width, 4), dtype=np.uint8)
            arr[:, :, :3] = rgb
            arr[:, :, 3] = 255
        if auto_crop:
            # Use single source of truth: cached box from original, scaled to thumb
            try:
                orig_box = get_cached_crop_box(image_path, threshold=15)
                if orig_box is not None:
                    # thumb is DOWN-scaled original, so scale box
                    import os as _os

                    # Get original dims via PIL for scaling (cheap, cached)
                    from PIL import Image as _PILImage

                    with _PILImage.open(image_path) as _im:
                        orig_w, orig_h = _im.size
                    scale_w = thumb.width / orig_w if orig_w else 1.0
                    scale_h = thumb.height / orig_h if orig_h else 1.0
                    l, t, r, b = orig_box
                    left = max(0, int(round(l * scale_w)))
                    top = max(0, int(round(t * scale_h)))
                    right = min(thumb.width, max(left + 1, int(round(r * scale_w))))
                    bottom = min(thumb.height, max(top + 1, int(round(b * scale_h))))
                    if (left, top, right, bottom) != (0, 0, thumb.width, thumb.height):
                        arr = arr[top:bottom, left:right]
                else:
                    # Fallback to direct probe if cache missed (e.g. JXL)
                    from shared.image_processing.tiled_pixel_store import _auto_crop_box_from_ndarray

                    box = _auto_crop_box_from_ndarray(arr)
                    if box is not None:
                        left, top, right, bottom = box
                        arr = arr[top:bottom, left:right]
            except Exception:
                from shared.image_processing.tiled_pixel_store import _auto_crop_box_from_ndarray

                box = _auto_crop_box_from_ndarray(arr)
                if box is not None:
                    left, top, right, bottom = box
                    arr = arr[top:bottom, left:right]
        return qimage_from_pixel_source(arr)
    except ImageSizeLimitError:
        raise
    except Exception as e:
        logger.error(f"Failed to load pyvips preview for {image_path}: {e}")
        return None


def get_image_dimensions(image_path: str) -> tuple[int, int] | None:
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            _ensure_supported_dimensions(width, height, image_path, ignore_limit=pyvips_can_stream(image_path))
            return (width, height)
    except ImageSizeLimitError:
        raise
    except Exception:
        if JXL_SUPPORTED and image_path.lower().endswith(".jxl"):
            try:
                decoded = imagecodecs.imread(image_path)
                height, width = decoded.shape[:2]
                _ensure_supported_dimensions(width, height, image_path, ignore_limit=pyvips_can_stream(image_path))
                return (width, height)
            except Exception as e:
                logger.error(f"Failed to read JXL dimensions {image_path}: {e}")
        return None

def get_image_format_info(image_path: str) -> tuple[str, bool, bool]:
    try:
        with Image.open(image_path) as img:
            format_name = img.format or "UNKNOWN"
            is_progressive = hasattr(img, "_get_loader") and "progressive" in str(
                img.info.get("progressive", 0)
            )

            return format_name, is_progressive, False
    except Exception:
        if image_path.lower().endswith(".jxl"):
            return "JXL", False, False
        return "UNKNOWN", False, False

class ProgressiveImageLoader:
    _FULL_CACHE_MAX = 8

    def __init__(self):
        from collections import OrderedDict
        from typing import TYPE_CHECKING
        if TYPE_CHECKING:
            from PySide6.QtGui import QImage
        self._preview_cache: dict[str, "QImage"] = {}
        self._full_cache: OrderedDict[str, object] = OrderedDict()

    def get_preview(
        self, image_path: str, force_reload: bool = False
    ) -> "QImage | None":
        if not force_reload and image_path in self._preview_cache:
            return self._preview_cache[image_path]
        preview = load_preview_image(image_path)
        if preview:
            self._preview_cache[image_path] = preview
        return preview

    def get_full(
        self, image_path: str, force_reload: bool = False, *, auto_crop: bool = False
    ):
        """Return a ``TiledPixelStore`` for ``image_path`` (cached, LRU-bounded)."""
        if not force_reload and image_path in self._full_cache:
            try:
                self._full_cache.move_to_end(image_path)
            except Exception:
                pass
            return self._full_cache[image_path]
        try:
            from shared.image_processing.tiled_pixel_store import TiledPixelStore

            store = TiledPixelStore.from_path(image_path, auto_crop=auto_crop)
        except ImageSizeLimitError:
            raise
        except Exception as e:
            logger.error(f"Failed to load full image {image_path}: {e}")
            return None
        if store is not None:
            self._full_cache[image_path] = store
            try:
                self._full_cache.move_to_end(image_path)
            except Exception:
                pass
            while len(self._full_cache) > self._FULL_CACHE_MAX:
                try:
                    _old_path, _old_store = self._full_cache.popitem(last=False)
                    from shared.image_processing.tiled_pixel_store import close_pixel_store

                    close_pixel_store(_old_store)
                except Exception:
                    break
        return store

    def clear_cache(self):
        from shared.image_processing.tiled_pixel_store import close_pixel_store

        for store in self._full_cache.values():
            close_pixel_store(store)
        self._preview_cache.clear()
        self._full_cache.clear()

    def invalidate_cache(self, image_path: str):
        from shared.image_processing.tiled_pixel_store import close_pixel_store

        old = self._full_cache.pop(image_path, None)
        close_pixel_store(old)
        self._preview_cache.pop(image_path, None)