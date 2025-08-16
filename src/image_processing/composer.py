import time
from typing import Callable, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageChops
from core.app_state import AppState
from core.constants import AppConstants
from image_processing.resize import get_pil_resampling_method
from image_processing.drawing.text_drawer import TextDrawer
from image_processing.drawing.magnifier_drawer import MagnifierDrawer, MIN_CAPTURE_THICKNESS
from PyQt6.QtCore import QPoint, QRect
import traceback
import math
import os
import sys
import logging

logger = logging.getLogger("ImproveImgSLI")

class ImageComposer:
    def __init__(self, font_path: str | None):
        if font_path is None or font_path == "":
            self.text_drawer = TextDrawer("")
        else:
            self.text_drawer = TextDrawer(font_path)
        self.magnifier_drawer = MagnifierDrawer()

    def create_base_split_image(
        self,
        image1_processed: Image.Image,
        image2_processed: Image.Image,
        split_position_visual: float,
        is_horizontal: bool,
    ) -> Image.Image | None:
        if not image1_processed or not image2_processed:
            return None

        try:
            if image1_processed.mode != "RGBA": image1_processed = image1_processed.convert("RGBA")
            if image2_processed.mode != "RGBA": image2_processed = image2_processed.convert("RGBA")

            if image1_processed.size != image2_processed.size:
                min_w = min(image1_processed.size[0], image2_processed.size[0])
                min_h = min(image1_processed.size[1], image2_processed.size[1])
                if min_w <= 0 or min_h <= 0:
                    return None
                if image1_processed.size != (min_w, min_h): image1_processed = image1_processed.resize((min_w, min_h), Image.Resampling.BILINEAR)
                if image2_processed.size != (min_w, min_h): image2_processed = image2_processed.resize((min_w, min_h), Image.Resampling.BILINEAR)
                if image1_processed.size != image2_processed.size:
                    return None

            width, height = image1_processed.size
            if width <= 0 or height <= 0:
                return None

            result = Image.new("RGBA", (width, height))
            if not is_horizontal:
                split_pos_abs = max(0, min(width, int(round(width * split_position_visual))))
                if split_pos_abs > 0: result.paste(image1_processed.crop((0, 0, split_pos_abs, height)), (0, 0))
                if split_pos_abs < width: result.paste(image2_processed.crop((split_pos_abs, 0, width, height)), (split_pos_abs, 0))
            else:
                split_pos_abs = max(0, min(height, int(round(height * split_position_visual))))
                if split_pos_abs > 0: result.paste(image1_processed.crop((0, 0, width, split_pos_abs)), (0, 0))
                if split_pos_abs < height: result.paste(image2_processed.crop((0, split_pos_abs, width, height)), (0, split_pos_abs))
            return result
        except Exception:
            return None

    def draw_split_line(
        self,
        image_to_draw_on: Image.Image,
        split_position_ratio: float,
        is_horizontal: bool,
        line_thickness: int = 3,
        blend_alpha: float = 0.5,
    ):
        if not isinstance(image_to_draw_on, Image.Image):
            return
        if image_to_draw_on.mode != "RGBA":
            try: image_to_draw_on = image_to_draw_on.convert("RGBA")
            except Exception:
                return
        width, height = image_to_draw_on.size
        if width <= 0 or height <= 0:
            return

        try:
            draw = ImageDraw.Draw(image_to_draw_on)
            line_color = (255, 255, 255, 255)

            if not is_horizontal:
                split_x = int(round(width * split_position_ratio))
                line_left = max(0, split_x - line_thickness // 2)
                line_right = min(width, split_x + (line_thickness + 1) // 2)
                if line_right > line_left and line_thickness > 0:
                    draw.rectangle([line_left, 0, line_right - 1, height - 1], fill=line_color)
            else:
                split_y = int(round(height * split_position_ratio))
                line_top = max(0, split_y - line_thickness // 2)
                line_bottom = min(height, split_y + (line_thickness + 1) // 2)
                if line_bottom > line_top and line_thickness > 0:
                    draw.rectangle([0, line_top, width - 1, line_bottom - 1], fill=line_color)
        except Exception:
            pass

    def generate_comparison_image(
        self,
        app_state: AppState,
        image1_scaled: Image.Image,
        image2_scaled: Image.Image,
        original_image1: Image.Image,
        original_image2: Image.Image,
        magnifier_drawing_coords: tuple | None,
        font_path_absolute: str | None,
        file_name1_text: str,
        file_name2_text: str,
    ) -> Tuple[Image.Image | None, int, int]:

        if not image1_scaled or not image2_scaled:
            return None, 0, 0

        try:
            img_w, img_h = image1_scaled.size

            padding_left, padding_top = 0, 0
            canvas_w, canvas_h = img_w, img_h

            if app_state.use_magnifier and magnifier_drawing_coords:
                magnifier_bbox = magnifier_drawing_coords[-1]
                if magnifier_bbox and not magnifier_bbox.isNull() and magnifier_bbox.isValid():
                    padding_left = abs(min(0, magnifier_bbox.left()))
                    padding_top = abs(min(0, magnifier_bbox.top()))
                    padding_right = max(0, magnifier_bbox.right() - img_w)
                    padding_bottom = max(0, magnifier_bbox.bottom() - img_h)
                    canvas_w = img_w + padding_left + padding_right
                    canvas_h = img_h + padding_top + padding_bottom

            final_canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
            image_paste_pos = (padding_left, padding_top)

            base_image_pil = self.create_base_split_image(
                image1_scaled, image2_scaled, app_state.split_position_visual, app_state.is_horizontal,
            )
            if not base_image_pil:
                return None, 0, 0

            line_thickness = min(7, max(1, int(min(img_w, img_h) * 0.005)))
            final_canvas.paste(base_image_pil, image_paste_pos)

            temp_draw_context = ImageDraw.Draw(final_canvas)

            if not app_state.is_horizontal:
                split_x_on_canvas = padding_left + int(round(img_w * app_state.split_position_visual))
                temp_draw_context.rectangle(
                    [
                        split_x_on_canvas - line_thickness // 2,
                        padding_top,
                        split_x_on_canvas + (line_thickness + 1) // 2 - 1,
                        padding_top + img_h - 1,
                    ],
                    fill=(255, 255, 255, 255),
                )
            else:
                split_y_on_canvas = padding_top + int(round(img_h * app_state.split_position_visual))
                temp_draw_context.rectangle(
                    [
                        padding_left,
                        split_y_on_canvas - line_thickness // 2,
                        padding_left + img_w - 1,
                        split_y_on_canvas + (line_thickness + 1) // 2 - 1,
                    ],
                    fill=(255, 255, 255, 255),
                )
            del temp_draw_context

            if app_state.use_magnifier and magnifier_drawing_coords and app_state.show_capture_area_on_main_image:
                on_screen_ref_dim = min(img_w, img_h)
                cap_size = max(5, int(round(app_state.capture_size_relative * on_screen_ref_dim)))
                cap_pos = QPoint(padding_left + int(round(app_state.capture_position_relative.x() * img_w)),
                                 padding_top + int(round(app_state.capture_position_relative.y() * img_h)))
                border_thickness_for_canvas = max(
                    int(MIN_CAPTURE_THICKNESS),
                    int(round(min(img_w, img_h) * 0.003))
                )

                self.magnifier_drawer.draw_capture_area(
                    final_canvas, cap_pos, cap_size, thickness=border_thickness_for_canvas
                )

            if app_state.use_magnifier and magnifier_drawing_coords:
                crop_box1, crop_box2, magn_mid_on_img, magn_size_pix, magn_spacing_pix, _ = magnifier_drawing_coords

                magn_mid_on_canvas = QPoint(magn_mid_on_img.x() + padding_left, magn_mid_on_img.y() + padding_top)

                should_combine_decision = app_state.magnifier_spacing_relative_visual < AppConstants.MIN_MAGNIFIER_SPACING_RELATIVE_FOR_COMBINE
                self.magnifier_drawer.draw_magnifier(
                    ImageDraw.Draw(final_canvas),
                    final_canvas, original_image1, original_image2,
                    crop_box1, crop_box2, magn_mid_on_canvas, magn_size_pix, magn_spacing_pix,
                    app_state.interpolation_method, app_state.is_horizontal, should_combine_decision,
                    app_state.is_interactive_mode,
                )

            if app_state.include_file_names_in_saved:
                image_rect_on_canvas = QRect(padding_left, padding_top, img_w, img_h)
                split_pos_on_canvas = (
                    padding_left + int(round(img_w * app_state.split_position_visual))
                    if not app_state.is_horizontal
                    else padding_top + int(round(img_h * app_state.split_position_visual))
                )
                self.text_drawer.draw_filenames_on_image(
                    app_state,
                    final_canvas,
                    image_rect_on_canvas,
                    split_pos_on_canvas,
                    line_thickness,
                    file_name1_text,
                    file_name2_text,
                )

            return final_canvas, padding_left, padding_top

        except Exception as e:
            traceback.print_exc()
            return None, 0, 0
