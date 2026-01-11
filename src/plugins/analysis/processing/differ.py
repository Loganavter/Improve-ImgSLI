

import logging
from typing import Optional

import numpy as np
from PIL import Image, ImageChops, ImageOps

logger = logging.getLogger("ImproveImgSLI")

def create_highlight_diff(
    image1: Image.Image,
    image2: Image.Image,
    threshold: int = 20,
    font_path: Optional[str] = None
) -> Optional[Image.Image]:
    """
    Создает изображение с подсвеченными различиями красным цветом.
    """
    if not image1 or not image2:
        return None

    if image1.size != image2.size:
        try:
            image2 = image2.resize(image1.size, Image.Resampling.LANCZOS)
        except Exception:
            return None

    try:
        img1_rgb = image1.convert("RGB")
        img2_rgb = image2.convert("RGB")
        diff = ImageChops.difference(img1_rgb, img2_rgb)

        diff_gray = diff.convert("L")

        highlight_mask = diff_gray.point(lambda p: 255 if p > threshold else 0)

        if highlight_mask.getbbox() is None:

            return image1.copy().convert("RGBA")

        red_overlay = Image.new("RGB", image1.size, (255, 90, 120))
        output_image = image1.copy()
        output_image.paste(red_overlay, mask=highlight_mask)
        return output_image.convert("RGBA")
    except Exception as e:
        logger.error(f"Error creating highlight diff: {e}", exc_info=True)
        return None

def create_grayscale_diff(
    image1: Image.Image,
    image2: Image.Image,
    font_path: Optional[str] = None
) -> Optional[Image.Image]:
    """
    Создает изображение различий в градациях серого.
    Усилен контраст для наглядности.
    """
    if not image1 or not image2:
        return None

    if image1.size != image2.size:
        try:
            image2 = image2.resize(image1.size, Image.Resampling.LANCZOS)
        except Exception:
            return None

    try:
        img1_rgb = image1.convert("RGB")
        img2_rgb = image2.convert("RGB")

        diff = ImageChops.difference(img1_rgb, img2_rgb)
        diff_gray = diff.convert("L")

        return ImageOps.autocontrast(diff_gray).convert("RGBA")
    except Exception as e:
        logger.error(f"Error creating grayscale diff: {e}", exc_info=True)
        return None

def create_ssim_map(
    image1: Image.Image,
    image2: Image.Image,
    font_path: Optional[str] = None
) -> Optional[Image.Image]:
    """
    Создает карту структурного сходства (SSIM).
    """
    if not image1 or not image2:
        return None

    if image1.size != image2.size:
        try:
            image2 = image2.resize(image1.size, Image.Resampling.LANCZOS)
        except Exception:
            return None

    try:
        from skimage.metrics import structural_similarity as ssim

        img1_rgb = image1.convert("RGB")
        img2_rgb = image2.convert("RGB")

        arr1 = np.array(img1_rgb)
        arr2 = np.array(img2_rgb)

        _, ssim_map = ssim(arr1, arr2, full=True, channel_axis=-1, data_range=255)

        if ssim_map.ndim == 3:
            ssim_map = np.mean(ssim_map, axis=2)

        diff_map = 1.0 - ssim_map

        heatmap_gray = (diff_map * 255).clip(0, 255).astype(np.uint8)

        heatmap_color = np.zeros((ssim_map.shape[0], ssim_map.shape[1], 3), dtype=np.uint8)

        heatmap_color[..., 0] = heatmap_gray
        heatmap_color[..., 1] = 0
        heatmap_color[..., 2] = heatmap_gray

        return Image.fromarray(heatmap_gray).convert("RGBA")

    except Exception as e:
        logger.error(f"Error creating SSIM map: {e}", exc_info=True)
        return None

