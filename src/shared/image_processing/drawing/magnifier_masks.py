import logging
import os
import sys

from PIL import Image, ImageDraw, ImageOps
from PyQt6.QtCore import QPoint

from utils.resource_loader import resource_path

logger = logging.getLogger("ImproveImgSLI")

_mask_image_cache = None
_mask_path_checked = False
_resized_mask_cache = {}

def _try_load_mask_from_path(mask_path: str):
    try:
        if os.path.exists(mask_path):
            rgba_mask = Image.open(mask_path)
            return (
                rgba_mask.getchannel("A")
                if "A" in rgba_mask.getbands()
                else ImageOps.invert(rgba_mask.convert("L"))
            )
    except Exception as e:
        logger.warning(f"Failed to load mask at {mask_path}: {e}")
    return None

def get_smooth_circular_mask(size: int) -> Image.Image | None:
    global _mask_image_cache, _mask_path_checked, _resized_mask_cache

    if size <= 0:
        return None
    if size in _resized_mask_cache:
        return _resized_mask_cache[size]

    if not _mask_path_checked:
        _mask_path_checked = True

        bundled_path = resource_path("resources/assets/circle_mask.png")
        _mask_image_cache = _try_load_mask_from_path(bundled_path)

        if _mask_image_cache is None:
            fallback_install_path = (
                "/app/lib/Improve-ImgSLI/resources/assets/circle_mask.png"
            )
            _mask_image_cache = _try_load_mask_from_path(fallback_install_path)
            if _mask_image_cache is None:
                fallback_install_path2 = "/app/lib/Improve-ImgSLI/assets/circle_mask.png"
                _mask_image_cache = _try_load_mask_from_path(fallback_install_path2)

        if _mask_image_cache is None:
            try:
                app_main_script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
                mask_path = os.path.join(
                    app_main_script_dir, "assets", "circle_mask.png"
                )
                _mask_image_cache = _try_load_mask_from_path(mask_path)
            except Exception as e:
                logger.debug(f"Error probing script-dir mask: {e}")

        if _mask_image_cache is None:
            logger.info(
                "Mask resource not found, will procedurally generate ellipse masks."
            )

    if _mask_image_cache:
        try:
            mask = _mask_image_cache.resize((size, size), Image.Resampling.LANCZOS)
            if len(_resized_mask_cache) > 50:
                _resized_mask_cache.clear()
            _resized_mask_cache[size] = mask
            return mask
        except Exception as e:
            logger.warning(f"Failed to resize cached mask, using generated: {e}")

    try:
        scale = 4
        big_size = size * scale
        prog_mask = Image.new("L", (big_size, big_size), 0)
        draw = ImageDraw.Draw(prog_mask)
        draw.ellipse((0, 0, big_size, big_size), fill=255)
        mask = prog_mask.resize((size, size), Image.Resampling.LANCZOS)
        if len(_resized_mask_cache) > 50:
            _resized_mask_cache.clear()
        _resized_mask_cache[size] = mask
        return mask
    except Exception as e:
        logger.error(f"Failed to generate fallback circular mask: {e}")
        return None

def create_framed_magnifier_widget(
    *,
    composite: Image.Image,
    magnifier_size_pixels: int,
    border_width: int,
    border_color: tuple,
) -> Image.Image | None:
    border_mask = get_smooth_circular_mask(magnifier_size_pixels)
    if not border_mask:
        return None
    final_magnifier_widget = Image.new(
        "RGBA", (magnifier_size_pixels, magnifier_size_pixels), border_color
    )
    final_magnifier_widget.putalpha(border_mask)
    paste_offset = border_width - 1
    final_magnifier_widget.paste(composite, (paste_offset, paste_offset), composite)
    return final_magnifier_widget

def paste_magnifier_widget(
    *,
    target_image: Image.Image,
    display_center_pos: QPoint,
    magnifier_widget: Image.Image | None,
):
    if magnifier_widget is None:
        return
    paste_x = display_center_pos.x() - (magnifier_widget.width // 2)
    paste_y = display_center_pos.y() - (magnifier_widget.height // 2)
    target_image.alpha_composite(magnifier_widget, (paste_x, paste_y))
