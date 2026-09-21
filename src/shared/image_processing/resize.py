import logging
import math
from typing import Optional, Tuple

from PIL import Image

from core.constants import AppConstants

logger = logging.getLogger("ImproveImgSLI")

def resample_image(
    pil_image: Image.Image,
    target_size: tuple[int, int],
    method_name: str,
    is_interactive_render: bool,
    diff_mode_active: bool = False,
) -> Image.Image:
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
    return pil_image.resize(target_size, selected_pil_method)

def resample_image_subpixel(
    pil_image: Image.Image,
    crop_box_float: tuple[float, float, float, float],
    target_size: tuple[int, int],
    method_name: str,
    is_interactive_render: bool,
    diff_mode_active: bool = False,
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

    left, top, right, bottom = (float(v) for v in crop_box_float)
    crop_w, crop_h = right - left, bottom - top
    if crop_w <= 0 or crop_h <= 0:
        return Image.new(pil_image.mode, target_size)

    # Honest subpixel crop: the old code truncated every coordinate with
    # int(), so boxes differing only fractionally (10.2 vs 10.7) produced
    # byte-identical output. Here the POSITION is subpixel-exact — the
    # expanded integer crop is translated by the fractional remainder
    # (BICUBIC ≈ ideal sinc shift) so an integer window aligns with the
    # float box — while the SIZE stays whole-px (the resize to target_size
    # absorbs the <1px rounding, same as any crop→resize step).
    pad = 2
    img_w, img_h = pil_image.width, pil_image.height
    ex0 = max(0, int(math.floor(left)) - pad)
    ey0 = max(0, int(math.floor(top)) - pad)
    ex1 = min(img_w, int(math.ceil(right)) + pad)
    ey1 = min(img_h, int(math.ceil(bottom)) + pad)

    if ex1 <= ex0 or ey1 <= ey0:
        return Image.new(pil_image.mode, target_size)

    expanded = pil_image.crop((ex0, ey0, ex1, ey1))

    fx0, fy0 = left - ex0, top - ey0
    frac_x = fx0 - math.floor(fx0)
    frac_y = fy0 - math.floor(fy0)
    if frac_x or frac_y:
        shift_filter = (
            Image.Resampling.NEAREST
            if str(method_name).upper() == "NEAREST"
            else Image.Resampling.BICUBIC
        )
        # Output (x, y) samples input (x + frac, y + frac): content moves
        # up-left by the fraction, landing the float origin on an integer.
        expanded = expanded.transform(
            expanded.size,
            Image.Transform.AFFINE,
            (1, 0, frac_x, 0, 1, frac_y),
            shift_filter,
        )

    wx0, wy0 = int(math.floor(fx0)), int(math.floor(fy0))
    wx1, wy1 = int(math.ceil(fx0 + crop_w)), int(math.ceil(fy0 + crop_h))
    wx0c, wy0c = max(0, wx0), max(0, wy0)
    wx1c, wy1c = min(expanded.width, wx1), min(expanded.height, wy1)
    if wx1c <= wx0c or wy1c <= wy0c:
        return Image.new(pil_image.mode, target_size)
    window = expanded.crop((wx0c, wy0c, wx1c, wy1c))

    return resample_image(
        window, target_size, method_name, is_interactive_render, diff_mode_active
    )

def resize_images_processor(
    original_image1: Image.Image | None,
    original_image2: Image.Image | None,
    method_name: str = "LANCZOS",
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
                final_processed_image1 = resample_image(
                    processed_img1_intermediate, target_size_final, method_name, False
                )
            else:
                final_processed_image1 = processed_img1_intermediate
        if processed_img2_intermediate:
            if processed_img2_intermediate.size != target_size_final:
                final_processed_image2 = resample_image(
                    processed_img2_intermediate, target_size_final, method_name, False
                )
            else:
                final_processed_image2 = processed_img2_intermediate
    except Exception as exc:
        logger.error("resample failed for target %s: %s", target_size_final, exc, exc_info=True)
        raise RuntimeError(f"Image unify/resample failed for {target_size_final}: {exc}") from exc

    if final_processed_image1:
        final_processed_image1.load()
    if final_processed_image2:
        final_processed_image2.load()

    return (final_processed_image1, final_processed_image2)
def get_auto_crop_box(
    pil_img: Image.Image, threshold: int = 15
) -> Optional[Tuple[int, int, int, int]]:
    try:
        analysis_img = pil_img.convert("RGB").convert("L")
        mask = analysis_img.point(lambda p: 255 if p > threshold else 0)
        bbox = mask.getbbox()
        if bbox and bbox != (0, 0, pil_img.width, pil_img.height):
            return bbox
        return None
    except Exception as e:
        logger.error(f"Error calculating crop box: {e}")
        return None

def crop_black_borders(pil_img: Image.Image, threshold: int = 15) -> Image.Image:
    try:
        bbox = get_auto_crop_box(pil_img, threshold)
        if bbox:
            logger.info(f"Auto-crop applied: {bbox} (Orig: {pil_img.size})")
            return pil_img.crop(bbox)
        return pil_img
    except Exception as e:
        logger.error(f"Error in crop_black_borders: {e}")
        return pil_img