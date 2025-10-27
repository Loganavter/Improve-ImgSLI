
import logging
from typing import Optional

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps, ImageStat

logger = logging.getLogger("ImproveImgSLI")

def create_highlight_diff(
    image1: Image.Image,
    image2: Image.Image,
    threshold: int = 20,
    font_path: Optional[str] = None
) -> Optional[Image.Image]:
    """
    Создает изображение с подсвеченными различиями красным цветом.

    Args:
        image1: Первое изображение
        image2: Второе изображение
        threshold: Порог для выделения различий (0-255)
        font_path: Путь к шрифту для текста "No significant differences found"

    Returns:
        Изображение с подсвеченными различиями или None при ошибке
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

        stat = ImageStat.Stat(diff)
        if all(mean_val < 2.0 for mean_val in stat.mean):
            no_diff_img = image1.copy().convert("RGBA")
            draw = ImageDraw.Draw(no_diff_img)

            try:
                font_size = max(24, int(min(image1.width, image1.height) * 0.05))
                font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
            except Exception:
                font = ImageFont.load_default()

            text = "No significant differences found"
            bbox = draw.textbbox((0,0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_pos = ((image1.width - text_width) // 2, (image1.height - text_height) // 2)

            draw.rectangle([text_pos[0]-10, text_pos[1]-10, text_pos[0]+text_width+10, text_pos[1]+text_height+10], fill=(0,0,0,128))
            draw.text(text_pos, text, font=font, fill=(255, 255, 255, 255))
            return no_diff_img

        diff_gray = diff.convert("L")
        highlight_mask = diff_gray.point(lambda p: 255 if p > threshold else 0)

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

    Args:
        image1: Первое изображение
        image2: Второе изображение
        font_path: Путь к шрифту для текста "No significant differences found"

    Returns:
        Изображение различий в градациях серого или None при ошибке
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

        stat = ImageStat.Stat(diff)
        if all(mean_val < 2.0 for mean_val in stat.mean):
            no_diff_img = image1.copy().convert("RGBA")
            draw = ImageDraw.Draw(no_diff_img)

            try:
                font_size = max(24, int(min(image1.width, image1.height) * 0.05))
                font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
            except Exception:
                font = ImageFont.load_default()

            text = "No significant differences found"
            bbox = draw.textbbox((0,0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_pos = ((image1.width - text_width) // 2, (image1.height - text_height) // 2)

            draw.rectangle([text_pos[0]-10, text_pos[1]-10, text_pos[0]+text_width+10, text_pos[1]+text_height+10], fill=(0,0,0,128))
            draw.text(text_pos, text, font=font, fill=(255, 255, 255, 255))
            return no_diff_img

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
    Создает карту структурного сходства (SSIM) между изображениями.

    Args:
        image1: Первое изображение
        image2: Второе изображение
        font_path: Путь к шрифту для текста "No significant differences found"

    Returns:
        Тепловая карта SSIM или None при ошибке
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
        diff = ImageChops.difference(img1_rgb, img2_rgb)

        stat = ImageStat.Stat(diff)
        if all(mean_val < 2.0 for mean_val in stat.mean):
            no_diff_img = image1.copy().convert("RGBA")
            draw = ImageDraw.Draw(no_diff_img)

            try:
                font_size = max(24, int(min(image1.width, image1.height) * 0.05))
                font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
            except Exception:
                font = ImageFont.load_default()

            text = "No significant differences found"
            bbox = draw.textbbox((0,0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_pos = ((image1.width - text_width) // 2, (image1.height - text_height) // 2)

            draw.rectangle([text_pos[0]-10, text_pos[1]-10, text_pos[0]+text_width+10, text_pos[1]+text_height+10], fill=(0,0,0,128))
            draw.text(text_pos, text, font=font, fill=(255, 255, 255, 255))
            return no_diff_img

        arr1 = np.array(img1_rgb)
        arr2 = np.array(img2_rgb)

        _, ssim_map = ssim(arr1, arr2, full=True, channel_axis=-1, data_range=255)

        if ssim_map.ndim == 3:
            ssim_map = ssim_map[..., 0]

        diff_map = 1 - ssim_map
        heatmap_gray = (diff_map * 127.5).astype(np.uint8)

        heatmap_color = np.zeros((ssim_map.shape[0], ssim_map.shape[1], 3), dtype=np.uint8)
        heatmap_color[..., 0] = heatmap_gray
        heatmap_color[..., 1] = 255 - heatmap_gray

        return Image.fromarray(heatmap_color).convert("RGBA")
    except Exception as e:
        logger.error(f"Error creating SSIM map: {e}", exc_info=True)
        return None

