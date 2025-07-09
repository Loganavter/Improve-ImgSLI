from PIL import Image
import traceback
from typing import Tuple
from services.state_manager import AppConstants
import logging

logger = logging.getLogger("ImproveImgSLI")

def get_pil_resampling_method(method_name: str, is_interactive_render: bool):
    method_map_base = {
        'NEAREST': Image.Resampling.NEAREST,
        'BILINEAR': Image.Resampling.BILINEAR,
        'BICUBIC': Image.Resampling.BICUBIC,
        'LANCZOS': Image.Resampling.LANCZOS}
    for key, _ in AppConstants.INTERPOLATION_METHODS_MAP.items():
        if key not in method_map_base and hasattr(Image.Resampling, key):
            method_map_base[key] = getattr(Image.Resampling, key)
    selected_pil_method = method_map_base.get(
        method_name.upper(), Image.Resampling.LANCZOS)
    final_method_for_pil = selected_pil_method
    if is_interactive_render:
        if selected_pil_method == Image.Resampling.NEAREST:
            final_method_for_pil = selected_pil_method
        else:
            final_method_for_pil = Image.Resampling.BILINEAR
    return final_method_for_pil
    return final_method_for_pil


def resize_images_processor(original_image1: Image.Image | None, original_image2: Image.Image |
                            None) -> Tuple[Image.Image | None, Image.Image | None]:
    processed_img1_intermediate = None
    if original_image1:
        if original_image1.mode != 'RGBA':
            processed_img1_intermediate = original_image1.convert('RGBA')
        else:
            processed_img1_intermediate = original_image1.copy()
    processed_img2_intermediate = None
    if original_image2:
        if original_image2.mode != 'RGBA':
            processed_img2_intermediate = original_image2.convert('RGBA')
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
    resampling_method_for_mode = get_pil_resampling_method(
        'LANCZOS', False)
    final_processed_image1 = None
    final_processed_image2 = None
    try:
        if processed_img1_intermediate:
            if processed_img1_intermediate.size != target_size_final:
                final_processed_image1 = processed_img1_intermediate.resize(
                    target_size_final, resampling_method_for_mode).copy()
            else:
                final_processed_image1 = processed_img1_intermediate
        if processed_img2_intermediate:
            if processed_img2_intermediate.size != target_size_final:
                final_processed_image2 = processed_img2_intermediate.resize(
                    target_size_final, resampling_method_for_mode).copy()
            else:
                final_processed_image2 = processed_img2_intermediate
    except Exception as e:
        logger.error(
            f'Error during resize_images_processor final processing/resizing: {e}')
        traceback.print_exc()
        return (processed_img1_intermediate, processed_img2_intermediate)
    return (final_processed_image1, final_processed_image2)