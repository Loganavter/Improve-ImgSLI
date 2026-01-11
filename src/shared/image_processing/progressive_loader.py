import logging
import os
from PIL import Image
from shared.image_processing.resize import crop_black_borders

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

def should_use_progressive_load(file_path: str, file_size_bytes: int | None = None) -> bool:
    if not file_path:
        return False

    if JXL_SUPPORTED and file_path.lower().endswith('.jxl'):
        return True

    if file_size_bytes is None:
        try:
            file_size_bytes = os.path.getsize(file_path)
        except OSError:
            file_size_bytes = 0

    from core.constants import AppConstants
    PROGRESSIVE_SIZE_THRESHOLD = getattr(AppConstants, 'PROGRESSIVE_LOAD_THRESHOLD_BYTES', 2 * 1024 * 1024)

    if file_size_bytes >= PROGRESSIVE_SIZE_THRESHOLD:
        return True

    try:

        with Image.open(file_path) as img:
            width, height = img.size
            FULL_HD_PIXELS = 1920 * 1080
            return (width * height) >= FULL_HD_PIXELS
    except Exception as e:

        if not file_path.lower().endswith('.jxl'):
            logger.debug(f"Failed to check image dimensions: {e}")
        return False

def load_preview_image(image_path: str, auto_crop: bool = False) -> Image.Image | None:
    try:

        if JXL_SUPPORTED and image_path.lower().endswith('.jxl'):
            logger.info(f"Loading JXL preview for: {image_path}")
            decoded = imagecodecs.imread(image_path)
            img = Image.fromarray(decoded)

            original_width, original_height = img.size
            max_preview_size = 1024
            scale = min(max_preview_size / original_width, max_preview_size / original_height)

            if scale < 1.0:
                new_width = int(original_width * scale)
                new_height = int(original_height * scale)
                img = img.resize((new_width, new_height), Image.Resampling.BILINEAR)

            preview = img.convert('RGBA')
            if auto_crop:
                preview = crop_black_borders(preview)
            preview.load()
            return preview

        with Image.open(image_path) as img:
            original_width, original_height = img.size
            max_preview_size = 1024
            scale = min(max_preview_size / original_width, max_preview_size / original_height)

            if scale >= 1.0:
                preview = img.copy().convert('RGBA')
            else:
                new_width = int(original_width * scale)
                new_height = int(original_height * scale)
                preview = img.copy()
                preview.thumbnail((new_width, new_height), Image.Resampling.BILINEAR)
                preview = preview.convert('RGBA')

            if auto_crop:
                preview = crop_black_borders(preview)
            preview.load()
            return preview
    except Exception as e:
        logger.error(f"Failed to load preview image {image_path}: {e}")
        return None

def load_full_image(image_path: str, auto_crop: bool = False) -> Image.Image | None:
    try:

        if JXL_SUPPORTED and image_path.lower().endswith('.jxl'):
            logger.info(f"Loading JXL full resolution: {image_path}")
            decoded = imagecodecs.imread(image_path)
            pil_img = Image.fromarray(decoded).convert("RGBA")
            if auto_crop:
                pil_img = crop_black_borders(pil_img)
            pil_img.load()
            return pil_img

        with Image.open(image_path) as img:
            img_to_process = img.copy()
            pil_img = img_to_process.convert("RGBA")
            if auto_crop:
                pil_img = crop_black_borders(pil_img)
            pil_img.load()
            return pil_img
    except Exception as e:
        logger.error(f"Failed to load full image {image_path}: {e}")
        return None

def get_image_format_info(image_path: str) -> tuple[str, bool, bool]:
    try:
        with Image.open(image_path) as img:
            format_name = img.format or 'UNKNOWN'
            is_progressive = hasattr(img, '_get_loader') and 'progressive' in str(img.info.get('progressive', 0))

            return format_name, is_progressive, False
    except:
        if image_path.lower().endswith('.jxl'): return 'JXL', False, False
        return 'UNKNOWN', False, False

class ProgressiveImageLoader:
    def __init__(self):
        self._preview_cache: dict[str, Image.Image] = {}
        self._full_cache: dict[str, Image.Image] = {}

    def get_preview(self, image_path: str, force_reload: bool = False) -> Image.Image | None:
        if not force_reload and image_path in self._preview_cache:
            return self._preview_cache[image_path]
        preview = load_preview_image(image_path)
        if preview: self._preview_cache[image_path] = preview
        return preview

    def get_full(self, image_path: str, force_reload: bool = False) -> Image.Image | None:
        if not force_reload and image_path in self._full_cache:
            return self._full_cache[image_path]
        full = load_full_image(image_path)
        if full: self._full_cache[image_path] = full
        return full

    def clear_cache(self):
        self._preview_cache.clear()
        self._full_cache.clear()

    def invalidate_cache(self, image_path: str):
        self._preview_cache.pop(image_path, None)
        self._full_cache.pop(image_path, None)
