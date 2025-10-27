import logging
from typing import Tuple

from PIL import Image

from core.constants import AppConstants

try:
    from wand.image import Image as WandImage
    WAND_AVAILABLE = True
except ImportError:
    WAND_AVAILABLE = False

logger = logging.getLogger("ImproveImgSLI")

if WAND_AVAILABLE:
    logger.info("Wand (ImageMagick) is available - EWA_LANCZOS will use high-quality resampling")
else:
    logger.info("Wand (ImageMagick) is not available - EWA_LANCZOS will fallback to Pillow LANCZOS")

def resample_image(pil_image: Image.Image, target_size: tuple[int, int], method_name: str, is_interactive_render: bool, diff_mode_active: bool = False) -> Image.Image:
    if method_name == "EWA_LANCZOS":
        if not WAND_AVAILABLE:
            logger.info("EWA_LANCZOS requested but Wand is not available, falling back to Pillow LANCZOS")
        else:
            try:

                import io
                img_buffer = io.BytesIO()
                pil_image.save(img_buffer, format='PNG')
                img_buffer.seek(0)

                with WandImage(blob=img_buffer.getvalue()) as img:
                    img.resize(target_size[0], target_size[1], 'lanczos')
                    img.format = 'png'
                    result = Image.open(io.BytesIO(img.make_blob()))

                    if result.mode != pil_image.mode:
                        logger.debug(f"EWA_LANCZOS changed mode from {pil_image.mode} to {result.mode}, converting back")
                        try:
                            result = result.convert(pil_image.mode)
                        except Exception as convert_error:
                            logger.warning(f"Failed to convert back to {pil_image.mode}: {convert_error}")

                            if pil_image.mode == 'RGBA':
                                result = result.convert('RGBA')

                    return result
            except Exception as e:
                logger.warning(f"Wand EWA_LANCZOS resampling failed, falling back to Pillow LANCZOS: {e}")

    method_map_base = {
        "NEAREST": Image.Resampling.NEAREST,
        "BILINEAR": Image.Resampling.BILINEAR,
        "BICUBIC": Image.Resampling.BICUBIC,
        "LANCZOS": Image.Resampling.LANCZOS,
        "EWA_LANCZOS": Image.Resampling.LANCZOS,
    }
    for key, _ in AppConstants.INTERPOLATION_METHODS_MAP.items():
        if key not in method_map_base and hasattr(Image.Resampling, key):
            method_map_base[key] = getattr(Image.Resampling, key)
    selected_pil_method = method_map_base.get(
        method_name.upper(), Image.Resampling.LANCZOS
    )
    final_method_for_pil = selected_pil_method

    return pil_image.resize(target_size, final_method_for_pil)

def resample_image_subpixel(
    pil_image: Image.Image,
    crop_box_float: tuple[float, float, float, float],
    target_size: tuple[int, int],
    method_name: str,
    is_interactive_render: bool,
    diff_mode_active: bool = False
) -> Image.Image:
    """
    Выполняет субпиксельный crop и масштабирование изображения (лёгкая версия).
    Использует расширенную crop-область вместо полного 4x масштабирования.

    Args:
        pil_image: Исходное изображение
        crop_box_float: Координаты crop-области (left, top, right, bottom) с float точностью
        target_size: Целевой размер результата
        method_name: Метод интерполяции
        is_interactive_render: Флаг интерактивного рендеринга
        diff_mode_active: Флаг активного diff режима

    Returns:
        Масштабированное изображение с учётом субпиксельных координат crop
    """
    if not pil_image or target_size[0] <= 0 or target_size[1] <= 0:
        return pil_image

    left = crop_box_float[0]
    top = crop_box_float[1]
    right = crop_box_float[2]
    bottom = crop_box_float[3]

    crop_w = right - left
    crop_h = bottom - top

    expand_pixels = 2

    expanded_left = max(0, int(left - expand_pixels))
    expanded_top = max(0, int(top - expand_pixels))
    expanded_right = min(pil_image.width, int(right + expand_pixels))
    expanded_bottom = min(pil_image.height, int(bottom + expand_pixels))

    expanded_cropped = pil_image.crop((expanded_left, expanded_top, expanded_right, expanded_bottom))

    subpixel_offset_x = left - expanded_left
    subpixel_offset_y = top - expanded_top

    final_left = int(subpixel_offset_x)
    final_top = int(subpixel_offset_y)
    final_right = int(subpixel_offset_x + crop_w)
    final_bottom = int(subpixel_offset_y + crop_h)

    compensate = 1
    cropped = expanded_cropped.crop((
        max(0, final_left - compensate),
        max(0, final_top - compensate),
        min(expanded_cropped.width, final_right + compensate),
        min(expanded_cropped.height, final_bottom + compensate)
    ))

    result = resample_image(cropped, target_size, method_name, is_interactive_render, diff_mode_active)

    return result

def resize_images_processor(
    original_image1: Image.Image | None, original_image2: Image.Image | None
) -> Tuple[Image.Image | None, Image.Image | None]:
    processed_img1_intermediate = None
    if original_image1:
        if original_image1.mode != "RGBA":
            processed_img1_intermediate = original_image1.convert("RGBA")
        else:
            processed_img1_intermediate = original_image1.copy()
    processed_img2_intermediate = None
    if original_image2:
        if original_image2.mode != "RGBA":
            processed_img2_intermediate = original_image2.convert("RGBA")
        else:
            processed_img2_intermediate = original_image2.copy()

    if not processed_img1_intermediate and (not processed_img2_intermediate):
        return (None, None)
    target_width = 0
    target_height = 0
    if processed_img1_intermediate:
        target_width = processed_img1_intermediate.width
        target_height = processed_img1_intermediate.height
    if processed_img2_intermediate:
        target_width = max(target_width, processed_img2_intermediate.width)
        target_height = max(target_height, processed_img2_intermediate.height)
    if target_width <= 0 or target_height <= 0:
        return (processed_img1_intermediate, processed_img2_intermediate)
    target_size_final = (target_width, target_height)

    final_processed_image1 = None
    final_processed_image2 = None
    try:
        if processed_img1_intermediate:
            if processed_img1_intermediate.size != target_size_final:
                final_processed_image1 = resample_image(processed_img1_intermediate, target_size_final, "LANCZOS", False)
            else:
                final_processed_image1 = processed_img1_intermediate
        if processed_img2_intermediate:
            if processed_img2_intermediate.size != target_size_final:
                final_processed_image2 = resample_image(processed_img2_intermediate, target_size_final, "LANCZOS", False)
            else:
                final_processed_image2 = processed_img2_intermediate
    except Exception:
        return (processed_img1_intermediate, processed_img2_intermediate)

    if final_processed_image1:
        final_processed_image1.load()
    if final_processed_image2:
        final_processed_image2.load()

    return (final_processed_image1, final_processed_image2)
