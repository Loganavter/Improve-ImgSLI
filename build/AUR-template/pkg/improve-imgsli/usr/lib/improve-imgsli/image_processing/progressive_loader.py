import logging
import os
import struct

from PIL import Image

logger = logging.getLogger("ImproveImgSLI")

def should_use_progressive_load(file_path: str, file_size_bytes: int | None = None) -> bool:
    """
    Определяет, нужно ли использовать прогрессивную загрузку для изображения.

    Args:
        file_path: Путь к файлу
        file_size_bytes: Размер файла в байтах (опционально)

    Returns:
        True если следует использовать прогрессивную загрузку
    """
    from core.constants import AppConstants

    if file_size_bytes is None:
        try:
            file_size_bytes = os.path.getsize(file_path)
        except OSError:
            file_size_bytes = 0

    PROGRESSIVE_SIZE_THRESHOLD = getattr(
        AppConstants,
        'PROGRESSIVE_LOAD_THRESHOLD_BYTES',
        2 * 1024 * 1024
    )

    if file_size_bytes >= PROGRESSIVE_SIZE_THRESHOLD:
        return True

    try:
        with Image.open(file_path) as img:
            width, height = img.size

            FULL_HD_PIXELS = 1920 * 1080
            total_pixels = width * height
            return total_pixels >= FULL_HD_PIXELS
    except Exception as e:
        logger.debug(f"Failed to check image dimensions: {e}")
        return False

def get_image_format_info(image_path: str) -> tuple[str, bool, bool]:
    """
    Получает информацию о формате изображения.

    Returns:
        Tuple (format_name, is_progressive, is_interlaced)
    """
    try:
        with Image.open(image_path) as img:
            format_name = img.format or 'UNKNOWN'
            is_progressive = hasattr(img, '_get_loader') and 'progressive' in str(img.info.get('progressive', 0))

            if format_name == 'JPEG':
                try:
                    with open(image_path, 'rb') as f:

                        data = f.read(1024)

                        if b'\xff\xc2' in data or b'\xff\xc4' in data:
                            is_progressive = True
                except Exception:
                    pass

            is_interlaced = False
            if format_name == 'PNG':
                try:
                    with open(image_path, 'rb') as f:

                        f.seek(16)
                        data = f.read(5)
                        if len(data) >= 5:
                            interlacing_method = data[4]
                            is_interlaced = interlacing_method == 1
                except Exception:
                    pass

            return format_name, is_progressive, is_interlaced
    except Exception as e:
        logger.warning(f"Failed to get image format info: {e}")
        return 'UNKNOWN', False, False

def load_preview_image(image_path: str) -> Image.Image | None:
    """
    Загружает preview изображение используя различные стратегии в зависимости от формата.

    Args:
        image_path: Путь к файлу изображения

    Returns:
        Preview изображение в низком разрешении или None
    """
    try:

        with Image.open(image_path) as img:
            format_name = img.format or 'UNKNOWN'

            original_width, original_height = img.size
            max_preview_size = 1024

            scale = min(
                max_preview_size / original_width,
                max_preview_size / original_height
            )

            if scale >= 1.0:

                preview = img.copy()
                preview = preview.convert('RGBA')
                preview.load()
                return preview
            else:

                new_width = int(original_width * scale)
                new_height = int(original_height * scale)

                preview = img.copy()
                preview.thumbnail((new_width, new_height), Image.Resampling.BILINEAR)
                preview = preview.convert('RGBA')

                preview.load()
                return preview
    except Exception as e:
        logger.error(f"Failed to load preview image: {e}")
        return None

def load_full_image(image_path: str) -> Image.Image | None:
    """
    Загружает полное изображение.

    Args:
        image_path: Путь к файлу изображения

    Returns:
        Полное изображение или None
    """
    try:
        with Image.open(image_path) as img:
            img_to_process = img.copy()
            pil_img = img_to_process.convert("RGBA")
            pil_img.load()
            return pil_img
    except Exception as e:
        logger.error(f"Failed to load full image: {e}")
        return None

class ProgressiveImageLoader:
    """
    Класс для управления прогрессивной загрузкой изображений.
    """

    def __init__(self):
        self._preview_cache: dict[str, Image.Image] = {}
        self._full_cache: dict[str, Image.Image] = {}

    def get_preview(self, image_path: str, force_reload: bool = False) -> Image.Image | None:
        """
        Получает preview изображения, используя кэш если возможно.

        Args:
            image_path: Путь к файлу
            force_reload: Принудительная перезагрузка

        Returns:
            Preview изображение
        """
        if not force_reload and image_path in self._preview_cache:
            return self._preview_cache[image_path]

        preview = load_preview_image(image_path)
        if preview:
            self._preview_cache[image_path] = preview
        return preview

    def get_full(self, image_path: str, force_reload: bool = False) -> Image.Image | None:
        """
        Получает полное изображение, используя кэш если возможно.

        Args:
            image_path: Путь к файлу
            force_reload: Принудительная перезагрузка

        Returns:
            Полное изображение
        """
        if not force_reload and image_path in self._full_cache:
            return self._full_cache[image_path]

        full = load_full_image(image_path)
        if full:
            self._full_cache[image_path] = full
        return full

    def clear_cache(self):
        """Очищает весь кэш загрузчика."""
        self._preview_cache.clear()
        self._full_cache.clear()

    def invalidate_cache(self, image_path: str):
        """Удаляет конкретное изображение из кэша."""
        self._preview_cache.pop(image_path, None)
        self._full_cache.pop(image_path, None)

