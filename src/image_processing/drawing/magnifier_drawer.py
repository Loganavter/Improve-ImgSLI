import time
from typing import Callable, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageChops

from image_processing.resize import get_pil_resampling_method
from PyQt6.QtCore import QPoint, QRect
import traceback
import math
import os
import sys
import logging
from utils.paths import resource_path

logger = logging.getLogger("ImproveImgSLI")

_mask_image_cache = None
_mask_path_checked = False
_resized_mask_cache = {}

CAPTURE_THICKNESS_FACTOR = 0.1
MIN_CAPTURE_THICKNESS = 2.0
MAX_CAPTURE_THICKNESS = 8.0

def _try_load_mask_from_path(mask_path: str):
    try:
        if os.path.exists(mask_path):
            rgba_mask = Image.open(mask_path)
            return rgba_mask.getchannel("A") if "A" in rgba_mask.getbands() else ImageOps.invert(rgba_mask.convert("L"))
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
            fallback_install_path = "/app/lib/Improve-ImgSLI/resources/assets/circle_mask.png"
            _mask_image_cache = _try_load_mask_from_path(fallback_install_path)
            if _mask_image_cache is None:
                fallback_install_path2 = "/app/lib/Improve-ImgSLI/assets/circle_mask.png"
                _mask_image_cache = _try_load_mask_from_path(fallback_install_path2)

        if _mask_image_cache is None:
            try:
                app_main_script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
                mask_path = os.path.join(app_main_script_dir, "assets", "circle_mask.png")
                _mask_image_cache = _try_load_mask_from_path(mask_path)
            except Exception as e:
                logger.debug(f"Error probing script-dir mask: {e}")

        if _mask_image_cache is None:
            logger.info("Mask resource not found, will procedurally generate ellipse masks.")

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

class MagnifierDrawer:
    def __init__(self):
        self._mask_image_cache = None
        self._mask_path_checked = False
        self._resized_mask_cache = {}

    def get_smooth_circular_mask(self, size: int) -> Image.Image | None:
        return get_smooth_circular_mask(size)

    def draw_capture_area(self, image_to_draw_on: Image.Image, center_pos: QPoint, size: int, thickness: int | None = None):
        if size <= 0 or center_pos is None or not isinstance(image_to_draw_on, Image.Image):
            return

        try:
            if thickness is None or thickness <= 0:
                thickness_float = CAPTURE_THICKNESS_FACTOR * math.sqrt(max(1.0, float(size)))
                thickness_clamped = max(float(MIN_CAPTURE_THICKNESS), min(float(MAX_CAPTURE_THICKNESS), thickness_float))
                thickness = max(2, int(round(thickness_clamped)))

            outer_size = size
            inner_size = size - thickness * 2
            if inner_size <= 0:
                return

            outer_mask = self.get_smooth_circular_mask(outer_size)
            if not outer_mask:
                return

            inner_mask_on_canvas = Image.new("L", (outer_size, outer_size), 0)
            inner_mask_small = self.get_smooth_circular_mask(inner_size)
            if not inner_mask_small:
                return
            inner_mask_on_canvas.paste(inner_mask_small, (thickness, thickness))

            donut_mask = ImageChops.subtract(outer_mask, inner_mask_on_canvas)
        except Exception:
            return

        ring_color = (255, 50, 100, 230)
        pastel_red_ring = Image.new("RGBA", (outer_size, outer_size), ring_color)

        paste_pos_x = center_pos.x() - outer_size // 2
        paste_pos_y = center_pos.y() - outer_size // 2

        try:
            image_to_draw_on.paste(pastel_red_ring, (paste_pos_x, paste_pos_y), donut_mask)
        except Exception:
            pass

        ring_color = (255, 50, 100, 230)
        pastel_red_ring = Image.new("RGBA", (outer_size, outer_size), ring_color)

        paste_pos_x = center_pos.x() - outer_size // 2
        paste_pos_y = center_pos.y() - outer_size // 2

        try:
            image_to_draw_on.paste(pastel_red_ring, (paste_pos_x, paste_pos_y), donut_mask)
        except Exception:
            pass

    def draw_magnifier(
        self,
        draw: ImageDraw.ImageDraw,
        image_to_draw_on: Image.Image,
        image1_for_crop: Image.Image,
        image2_for_crop: Image.Image,
        crop_box1: tuple,
        crop_box2: tuple,
        magnifier_midpoint_target: QPoint,
        magnifier_size_pixels: int,
        edge_spacing_pixels: int,
        interpolation_method: str,
        is_horizontal: bool,
        force_combine: bool,
        is_interactive_render: bool = False,
    ):
        if not all([image1_for_crop, image2_for_crop, crop_box1, crop_box2, magnifier_midpoint_target]) or magnifier_size_pixels <= 0:
            return
        if image_to_draw_on.mode != "RGBA":
            try:
                image_to_draw_on = image_to_draw_on.convert("RGBA")
            except Exception:
                return

        should_combine = force_combine

        if should_combine:
            try:
                self.draw_combined_magnifier_circle(
                    target_image=image_to_draw_on, display_center_pos=magnifier_midpoint_target,
                    crop_box1=crop_box1, crop_box2=crop_box2,
                    magnifier_size_pixels=magnifier_size_pixels,
                    image1_for_crop=image1_for_crop, image2_for_crop=image2_for_crop,
                    interpolation_method=interpolation_method, is_horizontal=is_horizontal,
                    is_interactive_render=is_interactive_render,
                )
            except Exception:
                pass
        else:
            try:
                radius = float(magnifier_size_pixels) / 2.0
                half_spacing = float(edge_spacing_pixels) / 2.0
                offset_from_midpoint = radius + half_spacing
                mid_x, mid_y = float(magnifier_midpoint_target.x()), float(magnifier_midpoint_target.y())

                left_center = QPoint(int(round(mid_x - offset_from_midpoint)), int(round(mid_y)))
                right_center = QPoint(int(round(mid_x + offset_from_midpoint)), int(round(mid_y)))

                self.draw_single_magnifier_circle(
                    target_image=image_to_draw_on, display_center_pos=left_center,
                    crop_box_orig=crop_box1, magnifier_size_pixels=magnifier_size_pixels,
                    image_for_crop=image1_for_crop, interpolation_method=interpolation_method,
                    is_interactive_render=is_interactive_render,
                )
                self.draw_single_magnifier_circle(
                    target_image=image_to_draw_on, display_center_pos=right_center,
                    crop_box_orig=crop_box2, magnifier_size_pixels=magnifier_size_pixels,
                    image_for_crop=image2_for_crop, interpolation_method=interpolation_method,
                    is_interactive_render=is_interactive_render,
                )
            except Exception:
                pass

    def draw_combined_magnifier_circle(
        self,
        target_image: Image.Image,
        display_center_pos: QPoint,
        crop_box1: tuple,
        crop_box2: tuple,
        magnifier_size_pixels: int,
        image1_for_crop: Image.Image,
        image2_for_crop: Image.Image,
        interpolation_method: str,
        is_horizontal: bool,
        is_interactive_render: bool = False,
    ):
        if not all([image1_for_crop, image2_for_crop, crop_box1, crop_box2, magnifier_size_pixels > 0]):
            return

        try:
            resampling_method = get_pil_resampling_method(interpolation_method, is_interactive_render)

            border_width = max(2, int(magnifier_size_pixels * 0.015))
            content_size = magnifier_size_pixels - border_width * 2 + 2
            if content_size <= 0:
                return

            scaled_content1 = image1_for_crop.crop(crop_box1).resize((content_size, content_size), resampling_method)
            scaled_content2 = image2_for_crop.crop(crop_box2).resize((content_size, content_size), resampling_method)

            content_mask = self.get_smooth_circular_mask(content_size)
            if not content_mask:
                return
            scaled_content1.putalpha(content_mask); scaled_content2.putalpha(content_mask)

            border_mask = self.get_smooth_circular_mask(magnifier_size_pixels)
            if not border_mask:
                return
            white_fill = Image.new("RGB", (magnifier_size_pixels, magnifier_size_pixels), (255, 255, 255))
            final_magnifier_widget = Image.new("RGBA", (magnifier_size_pixels, magnifier_size_pixels), (0, 0, 0, 0))
            final_magnifier_widget.paste(white_fill, (0, 0), border_mask)

            content_paste_pos = border_width - 1

            if not is_horizontal:
                half_content_width = content_size // 2
                left_half = scaled_content1.crop((0, 0, half_content_width, content_size))
                right_half = scaled_content2.crop((half_content_width, 0, content_size, content_size))
                final_magnifier_widget.paste(left_half, (content_paste_pos, content_paste_pos), mask=left_half)
                final_magnifier_widget.paste(right_half, (content_paste_pos + half_content_width, content_paste_pos), mask=right_half)

                line_thickness = max(1, int(border_width / 2))
                center_x = magnifier_size_pixels // 2
                line_image = Image.new("RGBA", (magnifier_size_pixels, magnifier_size_pixels), (0,0,0,0))
                ImageDraw.Draw(line_image).rectangle((center_x - line_thickness // 2, 0, center_x + (line_thickness + 1) // 2 - 1, magnifier_size_pixels), fill=(255, 255, 255, 230))
            else:
                half_content_height = content_size // 2
                top_half = scaled_content1.crop((0, 0, content_size, half_content_height))
                bottom_half = scaled_content2.crop((0, half_content_height, content_size, content_size))
                final_magnifier_widget.paste(top_half, (content_paste_pos, content_paste_pos), mask=top_half)
                final_magnifier_widget.paste(bottom_half, (content_paste_pos, content_paste_pos + half_content_height), mask=bottom_half)

                line_thickness = max(1, int(border_width / 2))
                center_y = magnifier_size_pixels // 2
                line_image = Image.new("RGBA", (magnifier_size_pixels, magnifier_size_pixels), (0,0,0,0))
                ImageDraw.Draw(line_image).rectangle((0, center_y - line_thickness // 2, magnifier_size_pixels, center_y + (line_thickness + 1) // 2 - 1), fill=(255, 255, 255, 230))

            line_mask_canvas = Image.new("L", (magnifier_size_pixels, magnifier_size_pixels), 0)
            line_mask_canvas.paste(content_mask, (content_paste_pos, content_paste_pos))
            line_image.putalpha(ImageChops.multiply(line_image.getchannel("A"), line_mask_canvas))
            final_magnifier_widget.alpha_composite(line_image, (0, 0))

            paste_x = display_center_pos.x() - (magnifier_size_pixels // 2)
            paste_y = display_center_pos.y() - (magnifier_size_pixels // 2)
            target_image.alpha_composite(final_magnifier_widget, (paste_x, paste_y))

        except Exception:
            pass

    def draw_single_magnifier_circle(
        self,
        target_image: Image.Image,
        display_center_pos: QPoint,
        crop_box_orig: tuple,
        magnifier_size_pixels: int,
        image_for_crop: Image.Image,
        interpolation_method: str,
        is_interactive_render: bool = False,
    ):
        if not isinstance(image_for_crop, Image.Image) or not crop_box_orig or magnifier_size_pixels <= 0:
            return

        try:
            resampling_method = get_pil_resampling_method(interpolation_method, is_interactive_render)

            border_width = max(2, int(magnifier_size_pixels * 0.015))
            content_size = magnifier_size_pixels - border_width * 2 + 2
            if content_size <= 0:
                return

            scaled_content = image_for_crop.crop(crop_box_orig).resize((content_size, content_size), resampling_method)

            content_mask = self.get_smooth_circular_mask(content_size)
            if not content_mask:
                return
            scaled_content.putalpha(content_mask)

            border_mask = self.get_smooth_circular_mask(magnifier_size_pixels)
            if not border_mask:
                return
            white_fill = Image.new("RGB", (magnifier_size_pixels, magnifier_size_pixels), (255, 255, 255))
            final_magnifier_widget = Image.new("RGBA", (magnifier_size_pixels, magnifier_size_pixels), (0, 0, 0, 0))
            final_magnifier_widget.paste(white_fill, (0, 0), border_mask)

            content_paste_pos = border_width - 1
            final_magnifier_widget.alpha_composite(scaled_content, (content_paste_pos, content_paste_pos))

            paste_x = display_center_pos.x() - (magnifier_size_pixels // 2)
            paste_y = display_center_pos.y() - (magnifier_size_pixels // 2)
            target_image.alpha_composite(final_magnifier_widget, (paste_x, paste_y))

        except Exception:
            pass
