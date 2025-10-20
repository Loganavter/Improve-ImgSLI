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
