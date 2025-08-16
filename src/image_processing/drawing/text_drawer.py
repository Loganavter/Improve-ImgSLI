import time
from typing import Callable, Tuple
from PIL import Image, ImageDraw, ImageFont
from core.app_state import AppState
from utils.resource_loader import truncate_text
from PyQt6.QtCore import QRect
import traceback
import os
import logging

logger = logging.getLogger("ImproveImgSLI")

FontType = ImageFont.FreeTypeFont
GetSizeFuncType = Callable[[str, FontType], Tuple[int, int]]

TEXT_BG_SMOOTHING_FACTOR = 0.2

_nine_slice_template_cache = {}

def create_nine_slice_template(radius: int, fill: tuple, scale: int = 4) -> Image.Image:
    cache_key = (radius, fill, scale)
    if cache_key in _nine_slice_template_cache:
        return _nine_slice_template_cache[cache_key]

    hr_radius = radius * scale
    hr_size = hr_radius * 2 + scale

    hr_canvas = Image.new("RGBA", (hr_size, hr_size), (0, 0, 0, 0))
    hr_draw = ImageDraw.Draw(hr_canvas)

    hr_draw.rounded_rectangle((0, 0, hr_size, hr_size), radius=hr_radius, fill=fill)

    template = hr_canvas.resize((radius * 2 + 1, radius * 2 + 1), Image.Resampling.LANCZOS)
    _nine_slice_template_cache[cache_key] = template
    return template

def draw_nine_slice_rounded_rect(target_image: Image.Image, rect: list, radius: int, fill: tuple):
    if not fill or len(fill) < 4 or fill[3] == 0:
        return

    left, top, right, bottom = map(int, rect)
    width = right - left
    height = bottom - top

    if width <= 0 or height <= 0 or radius <= 0:
        return

    template = create_nine_slice_template(radius, fill)
    template_size = template.width

    c = radius

    if width < 2 * c or height < 2 * c:
        scaled_rect = template.resize((width, height), Image.Resampling.LANCZOS)
        target_image.alpha_composite(scaled_rect, (left, top))
        return

    top_left_c = (0, 0, c, c)
    top_right_c = (c + 1, 0, template_size, c)
    bottom_left_c = (0, c + 1, c, template_size)
    bottom_right_c = (c + 1, c + 1, template_size, template_size)

    top_e = (c, 0, c + 1, c)
    left_e = (0, c, c, c + 1)
    right_e = (c + 1, c, template_size, c + 1)
    bottom_e = (c, c + 1, c + 1, template_size)

    center_p = (c, c, c + 1, c + 1)

    corners = {
        'tl': template.crop(top_left_c),
        'tr': template.crop(top_right_c),
        'bl': template.crop(bottom_left_c),
        'br': template.crop(bottom_right_c)
    }
    edges = {
        't': template.crop(top_e),
        'l': template.crop(left_e),
        'r': template.crop(right_e),
        'b': template.crop(bottom_e)
    }
    center = template.crop(center_p)

    center_w = width - 2 * c
    center_h = height - 2 * c

    target_image.alpha_composite(corners['tl'], (left, top))
    target_image.alpha_composite(corners['tr'], (left + width - c, top))
    target_image.alpha_composite(corners['bl'], (left, top + height - c))
    target_image.alpha_composite(corners['br'], (left + width - c, top + height - c))

    if center_w > 0:
        target_image.alpha_composite(edges['t'].resize((center_w, c)), (left + c, top))
        target_image.alpha_composite(edges['b'].resize((center_w, c)), (left + c, top + height - c))

    if center_h > 0:
        target_image.alpha_composite(edges['l'].resize((c, center_h)), (left, top + c))
        target_image.alpha_composite(edges['r'].resize((c, center_h)), (left + width - c, top + c))

    if center_w > 0 and center_h > 0:
        target_image.alpha_composite(center.resize((center_w, center_h)), (left + c, top + c))

class TextDrawer:
    def __init__(self, font_path: str | None):
        self._font_path = font_path if font_path else ""
        self._font_cache = {}
        self._text_size_cache = {}

    def _get_cached_font(self, size: int, use_antialiasing: bool = False) -> FontType:
        cache_key = (size, use_antialiasing)
        if cache_key not in self._font_cache:
            try:
                if self._font_path and os.path.exists(self._font_path):
                    self._font_cache[cache_key] = ImageFont.truetype(self._font_path, size)
                else:
                    self._font_cache[cache_key] = ImageFont.load_default()
            except Exception as e:
                self._font_cache[cache_key] = ImageFont.load_default()
        return self._font_cache[cache_key]

    def _get_cached_text_size(self, text: str, font: FontType, font_weight: int, draw_context: ImageDraw.ImageDraw = None) -> Tuple[int, int]:
        cache_key = (text, font.path if hasattr(font, 'path') else str(font), font.size, font_weight)
        if cache_key not in self._text_size_cache:
            self._text_size_cache[cache_key] = self._internal_get_text_size(text, font, font_weight, draw_context)
        return self._text_size_cache[cache_key]

    def _internal_get_text_size(self, text: str, font_to_use: FontType, font_weight: int, draw_context: ImageDraw.ImageDraw = None) -> Tuple[int, int]:
        try:
            if font_weight > 0:
                SUPER_SAMPLE_FACTOR = 4
                high_res_font = self._get_cached_font(font_to_use.size * SUPER_SAMPLE_FACTOR)

                desired_stroke_float = (font_to_use.size / 2000.0) * font_weight
                high_res_stroke_int = max(0, int(round(desired_stroke_float * SUPER_SAMPLE_FACTOR)))

                try:
                    hr_bbox = high_res_font.getbbox(text, stroke_width=high_res_stroke_int)
                except (TypeError, AttributeError):
                    if not draw_context:
                        dummy_image = Image.new('RGBA', (1, 1))
                        draw_context = ImageDraw.Draw(dummy_image)
                    hr_bbox = draw_context.textbbox((0, 0), text, font=high_res_font, stroke_width=high_res_stroke_int)

                width = (hr_bbox[2] - hr_bbox[0]) / SUPER_SAMPLE_FACTOR
                height = (hr_bbox[3] - hr_bbox[1]) / SUPER_SAMPLE_FACTOR
                return int(round(width)), int(round(height))
            else:
                if not draw_context:
                    dummy_image = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
                    draw_context = ImageDraw.Draw(dummy_image)
                bbox = draw_context.textbbox((0, 0), text, font=font_to_use)
                return bbox[2] - bbox[0], bbox[3] - bbox[1]
        except Exception as e:
            return len(text) * font_to_use.size // 2, font_to_use.size

    def _draw_text_with_supersampling_stroke(self, target_image: Image.Image, xy: tuple[int, int], text: str, font: FontType, anchor: str, fill_color: tuple, font_weight: int, global_alpha_int: int):

        try:
            base_r, base_g, base_b = fill_color[0], fill_color[1], fill_color[2]
            base_a = fill_color[3] if len(fill_color) >= 4 else 255
        except Exception:
            base_r, base_g, base_b, base_a = 255, 255, 255, 255
        try:
            ga = max(0, min(255, int(global_alpha_int)))
        except Exception:
            ga = 255
        final_alpha_mul = (base_a * ga) // 255

        if font_weight <= 0:

            try:
                overlay = Image.new("RGBA", target_image.size, (0, 0, 0, 0))
                overlay_draw = ImageDraw.Draw(overlay)

                overlay_draw.text(xy, text, fill=(base_r, base_g, base_b, 255), font=font, anchor=anchor)

                if final_alpha_mul < 255:
                    try:
                        a = overlay.split()[3]
                        a = a.point(lambda p: (p * final_alpha_mul) // 255)
                        overlay.putalpha(a)
                    except Exception:
                        pass
                target_image.alpha_composite(overlay)
            except Exception:
                pass
            return

        SUPER_SAMPLE_FACTOR = 4
        high_res_font = self._get_cached_font(font.size * SUPER_SAMPLE_FACTOR)
        if not high_res_font:
            try:
                overlay = Image.new("RGBA", target_image.size, (0, 0, 0, 0))
                ImageDraw.Draw(overlay).text(xy, text, fill=(base_r, base_g, base_b, 255), font=font, anchor=anchor)
                if final_alpha_mul < 255:
                    try:
                        a = overlay.split()[3]
                        a = a.point(lambda p: (p * final_alpha_mul) // 255)
                        overlay.putalpha(a)
                    except Exception:
                        pass
                target_image.alpha_composite(overlay)
            except Exception:
                pass
            return

        fill_color_rgba = (base_r, base_g, base_b, 255)
        desired_stroke_float = (font.size / 2000.0) * font_weight
        high_res_stroke_int = max(0, int(round(desired_stroke_float * SUPER_SAMPLE_FACTOR)))

        try:
            hr_bbox = high_res_font.getbbox(text, anchor=anchor, stroke_width=high_res_stroke_int)
        except (TypeError, AttributeError):
            try:
                hr_bbox = ImageDraw.Draw(Image.new("RGBA", (1,1))).textbbox((0,0), text, font=high_res_font, anchor=anchor, stroke_width=high_res_stroke_int)
            except Exception:
                return

        hr_width, hr_height = hr_bbox[2] - hr_bbox[0], hr_bbox[3] - hr_bbox[1]
        if hr_width <= 0 or hr_height <= 0:
            return

        try:
            temp_hr_img = Image.new("RGBA", (hr_width, hr_height), (0,0,0,0))
            temp_hr_draw = ImageDraw.Draw(temp_hr_img)
            temp_hr_draw.text((-hr_bbox[0], -hr_bbox[1]), text, fill=fill_color_rgba, font=high_res_font, anchor=anchor, stroke_width=high_res_stroke_int, stroke_fill=fill_color_rgba)
            final_size = (int(round(hr_width / SUPER_SAMPLE_FACTOR)), int(round(hr_height / SUPER_SAMPLE_FACTOR)))
            if final_size[0] <= 0 or final_size[1] <= 0: return

            scaled_text_img = temp_hr_img.resize(final_size, Image.Resampling.LANCZOS)

            if final_alpha_mul < 255:
                try:
                    a = scaled_text_img.split()[3]
                    a = a.point(lambda p: (p * final_alpha_mul) // 255)
                    scaled_text_img.putalpha(a)
                except Exception:
                    pass
            paste_pos = (int(round(xy[0] + hr_bbox[0] / SUPER_SAMPLE_FACTOR)), int(round(xy[1] + hr_bbox[1] / SUPER_SAMPLE_FACTOR)))
            target_image.alpha_composite(scaled_text_img, paste_pos)
        except Exception:
            pass

    def _draw_vertical_filenames(
        self,
        app_state: AppState,
        target_image: Image.Image,
        font: FontType,
        file_name1: str, file_name2: str,
        split_pos: int, line_width: int, margin: int, image_rect: QRect,
        text_color: tuple, text_bg_color: tuple, font_weight: int,
        visual_text_h: float
    ):
        BG_PADDING_X = 8
        BG_PADDING_Y = 4
        BG_RADIUS = 6

        y_text_area_bottom = image_rect.bottom() - margin
        bg_height = visual_text_h + 2 * BG_PADDING_Y

        if file_name1:
            try:
                draw_context = ImageDraw.Draw(target_image)
                text_w1, _ = self._get_cached_text_size(file_name1, font, font_weight, draw_context)
                bg_width = text_w1 + 2 * BG_PADDING_X

                bg_x_left, bg_x_right = 0, 0
                if app_state.text_placement_mode == "split_line":
                    bg_x_right = split_pos - line_width // 2 - margin
                    bg_x_left = bg_x_right - bg_width
                else:
                    bg_x_left = image_rect.left() + margin
                    bg_x_right = bg_x_left + bg_width

                bg_rect1 = [
                    max(image_rect.left(), bg_x_left),
                    max(image_rect.top(), int(y_text_area_bottom - bg_height)),
                    min(split_pos - line_width//2, bg_x_right),
                    y_text_area_bottom,
                ]

                if app_state.draw_text_background and text_bg_color and len(text_bg_color) == 4 and text_bg_color[3] > 0:

                    br, bg, bb, ba = text_bg_color
                    eff_bg_a = int(round((ba * app_state.text_alpha_percent) / 100.0))
                    if eff_bg_a > 0:
                        draw_nine_slice_rounded_rect(target_image, bg_rect1, BG_RADIUS, (br, bg, bb, eff_bg_a))

                text_draw_x = bg_rect1[0] + (bg_rect1[2] - bg_rect1[0]) / 2
                text_draw_y = bg_rect1[1] + (bg_rect1[3] - bg_rect1[1]) / 2

                _, _, _, ca = text_color if len(text_color) == 4 else (*text_color, 255)
                global_alpha_int = int(round((ca * app_state.text_alpha_percent) / 100.0))
                self._draw_text_with_supersampling_stroke(target_image, (int(text_draw_x), int(text_draw_y)), file_name1, font, "mm", text_color, font_weight, global_alpha_int)
            except Exception:
                pass

        if file_name2:
            try:
                draw_context = ImageDraw.Draw(target_image)
                text_w2, _ = self._get_cached_text_size(file_name2, font, font_weight, draw_context)
                bg_width = text_w2 + 2 * BG_PADDING_X

                bg_x_left, bg_x_right = 0, 0
                if app_state.text_placement_mode == "split_line":
                    bg_x_left = split_pos + (line_width + 1) // 2 + margin
                    bg_x_right = bg_x_left + bg_width
                else:
                    bg_x_right = image_rect.right() - margin
                    bg_x_left = bg_x_right - bg_width

                bg_rect2 = [
                    max(split_pos + (line_width + 1) // 2, bg_x_left),
                    max(image_rect.top(), int(y_text_area_bottom - bg_height)),
                    min(image_rect.right(), bg_x_right),
                    y_text_area_bottom,
                ]

                if app_state.draw_text_background and text_bg_color and len(text_bg_color) == 4 and text_bg_color[3] > 0:
                    br, bg, bb, ba = text_bg_color
                    eff_bg_a = int(round((ba * app_state.text_alpha_percent) / 100.0))
                    if eff_bg_a > 0:
                        draw_nine_slice_rounded_rect(target_image, bg_rect2, BG_RADIUS, (br, bg, bb, eff_bg_a))

                text_draw_x = bg_rect2[0] + (bg_rect2[2] - bg_rect2[0]) / 2
                text_draw_y = bg_rect2[1] + (bg_rect2[3] - bg_rect2[1]) / 2

                _, _, _, ca = text_color if len(text_color) == 4 else (*text_color, 255)
                global_alpha_int = int(round((ca * app_state.text_alpha_percent) / 100.0))
                self._draw_text_with_supersampling_stroke(target_image, (int(text_draw_x), int(text_draw_y)), file_name2, font, "mm", text_color, font_weight, global_alpha_int)
            except Exception:
                pass

    def _draw_horizontal_filenames(
        self,
        app_state: AppState,
        target_image: Image.Image,
        font: FontType,
        file_name1: str, file_name2: str,
        split_pos: int, line_height: int, margin: int, image_rect: QRect,
        text_color: tuple, text_bg_color: tuple, font_weight: int,
        text_w1: int, text_w2: int
    ):
        BG_PADDING_X = 8
        BG_PADDING_Y = 4
        BG_RADIUS = 6

        center_x = image_rect.left() + image_rect.width() // 2

        if file_name1:
            try:
                draw_context = ImageDraw.Draw(target_image)
                _, text_h1 = self._get_cached_text_size(file_name1, font, font_weight, draw_context)

                bg_height = text_h1 + 2 * BG_PADDING_Y
                bg_width = text_w1 + 2 * BG_PADDING_X

                bg_x_left = int(center_x - bg_width / 2.0)

                bg_y_top, bg_y_bottom_limit = 0, 0

                if app_state.text_placement_mode == "split_line":
                    y1_text_area_bottom = split_pos - line_height // 2 - margin
                    bg_y_top = max(image_rect.top(), y1_text_area_bottom - bg_height)
                    bg_y_bottom_limit = split_pos - line_height // 2
                else:
                    y1_text_area_top = image_rect.top() + margin
                    bg_y_top = max(image_rect.top(), y1_text_area_top - BG_PADDING_Y)
                    bg_y_bottom_limit = split_pos - line_height // 2

                bg_rect1 = [
                    max(image_rect.left(), bg_x_left),
                    bg_y_top,
                    min(image_rect.right(), bg_x_left + bg_width),
                    min(bg_y_bottom_limit, bg_y_top + bg_height),
                ]

                if app_state.draw_text_background and text_bg_color and len(text_bg_color) == 4 and text_bg_color[3] > 0:
                    br, bg, bb, ba = text_bg_color
                    eff_bg_a = int(round((ba * app_state.text_alpha_percent) / 100.0))
                    if eff_bg_a > 0:
                        draw_nine_slice_rounded_rect(target_image, bg_rect1, BG_RADIUS, (br, bg, bb, eff_bg_a))

                text_draw_x = bg_rect1[0] + (bg_rect1[2] - bg_rect1[0]) / 2
                text_draw_y = bg_rect1[1] + (bg_rect1[3] - bg_rect1[1]) / 2

                _, _, _, ca = text_color if len(text_color) == 4 else (*text_color, 255)
                global_alpha_int = int(round((ca * app_state.text_alpha_percent) / 100.0))
                self._draw_text_with_supersampling_stroke(target_image, (int(text_draw_x), int(text_draw_y)), file_name1, font, "mm", text_color, font_weight, global_alpha_int)
            except Exception:
                pass

        if file_name2:
            try:
                draw_context = ImageDraw.Draw(target_image)
                _, text_h2 = self._get_cached_text_size(file_name2, font, font_weight, draw_context)

                bg_height = text_h2 + 2 * BG_PADDING_Y
                bg_width = text_w2 + 2 * BG_PADDING_X

                bg_x_left = int(center_x - bg_width / 2.0)

                bg_y_top, bg_y_bottom = 0, 0
                if app_state.text_placement_mode == "split_line":
                    y2_text_area_top = split_pos + (line_height + 1) // 2 + margin
                    bg_y_top = max(image_rect.top(), y2_text_area_top - BG_PADDING_Y)
                    bg_y_bottom = min(image_rect.bottom(), bg_y_top + bg_height)
                else:
                    y2_text_area_bottom = image_rect.bottom() - margin
                    bg_y_bottom = min(image_rect.bottom(), y2_text_area_bottom + BG_PADDING_Y)
                    bg_y_top = max(image_rect.top(), bg_y_bottom - bg_height)

                bg_rect2 = [
                    max(image_rect.left(), bg_x_left),
                    bg_y_top,
                    min(image_rect.right(), bg_x_left + bg_width),
                    bg_y_bottom,
                ]

                if app_state.draw_text_background and text_bg_color and len(text_bg_color) == 4 and text_bg_color[3] > 0:
                    br, bg, bb, ba = text_bg_color
                    eff_bg_a = int(round((ba * app_state.text_alpha_percent) / 100.0))
                    if eff_bg_a > 0:
                        draw_nine_slice_rounded_rect(target_image, bg_rect2, BG_RADIUS, (br, bg, bb, eff_bg_a))

                text_draw_x = bg_rect2[0] + (bg_rect2[2] - bg_rect2[0]) / 2
                text_draw_y = bg_rect2[1] + (bg_rect2[3] - bg_rect2[1]) / 2

                _, _, _, ca = text_color if len(text_color) == 4 else (*text_color, 255)
                global_alpha_int = int(round((ca * app_state.text_alpha_percent) / 100.0))
                self._draw_text_with_supersampling_stroke(target_image, (int(text_draw_x), int(text_draw_y)), file_name2, font, "mm", text_color, font_weight, global_alpha_int)
            except Exception:
                pass

    def draw_filenames_on_image(
        self,
        app_state: AppState,
        target_image: Image.Image,
        image_rect_on_canvas: QRect,
        split_position_on_canvas: int,
        line_thickness: int,
        file_name1_text: str,
        file_name2_text: str,
    ):
        try:
            if not app_state.include_file_names_in_saved:
                return

            draw_context = ImageDraw.Draw(target_image)
            reference_size = min(image_rect_on_canvas.height(), image_rect_on_canvas.width())
            base_font_size_px = max(10, reference_size * 0.04)
            font_size = int(round(base_font_size_px * (app_state.font_size_percent / 100.0)))
            font_size = max(8, font_size)

            margin = max(5, int(font_size * 0.25)) + 5
            font = self._get_cached_font(font_size, not app_state.is_interactive_mode)
            if not font: return

            MIN_DRAWABLE_WIDTH = font_size * 1.5

            font_weight = app_state.font_weight
            full_w1, full_h1 = self._get_cached_text_size(file_name1_text, font, font_weight, draw_context)
            full_w2, full_h2 = self._get_cached_text_size(file_name2_text, font, font_weight, draw_context)

            if not app_state.is_horizontal:
                available_width1 = max(10, (split_position_on_canvas - image_rect_on_canvas.left()) - line_thickness / 2 - margin * 2)
                available_width2 = max(10, (image_rect_on_canvas.right() - (split_position_on_canvas + line_thickness / 2)) - margin * 2)

                if available_width1 < MIN_DRAWABLE_WIDTH:
                    truncated_name1 = ""
                else:
                    truncated_name1 = file_name1_text if full_w1 <= available_width1 else truncate_text(file_name1_text, available_width1, app_state.max_name_length, font, lambda t, f: self._get_cached_text_size(t, f, font_weight, draw_context))

                if available_width2 < MIN_DRAWABLE_WIDTH:
                    truncated_name2 = ""
                else:
                    truncated_name2 = file_name2_text if full_w2 <= available_width2 else truncate_text(file_name2_text, available_width2, app_state.max_name_length, font, lambda t, f: self._get_cached_text_size(t, f, font_weight, draw_context))

                target_h = max(full_h1, full_h2)
                current_visual_h = app_state.text_bg_visual_height
                new_visual_h = target_h if target_h > current_visual_h else current_visual_h + (target_h - current_visual_h) * TEXT_BG_SMOOTHING_FACTOR
                app_state.text_bg_visual_height = new_visual_h

                self._draw_vertical_filenames(
                    app_state,
                    target_image,
                    font,
                    truncated_name1,
                    truncated_name2,
                    split_position_on_canvas,
                    line_thickness,
                    margin,
                    image_rect_on_canvas,
                    app_state.file_name_color.getRgb(),
                    app_state.file_name_bg_color.getRgb(),
                    app_state.font_weight,
                    new_visual_h
                )
            else:
                available_width = max(10, image_rect_on_canvas.width() - margin * 2)

                if available_width < MIN_DRAWABLE_WIDTH:
                    truncated_name1 = ""
                    truncated_name2 = ""
                else:
                    truncated_name1 = file_name1_text if full_w1 <= available_width else truncate_text(file_name1_text, available_width, app_state.max_name_length, font, lambda t, f: self._get_cached_text_size(t, f, font_weight, draw_context))
                    truncated_name2 = file_name2_text if full_w2 <= available_width else truncate_text(file_name2_text, available_width, app_state.max_name_length, font, lambda t, f: self._get_cached_text_size(t, f, font_weight, draw_context))

                w1 = self._get_cached_text_size(truncated_name1, font, font_weight, draw_context)[0]
                w2 = self._get_cached_text_size(truncated_name2, font, font_weight, draw_context)[0]
                target_w = max(w1, w2)
                current_visual_w = app_state.text_bg_visual_width
                new_visual_w = target_w if target_w > current_visual_w else current_visual_w + (target_w - current_visual_w) * TEXT_BG_SMOOTHING_FACTOR
                app_state.text_bg_visual_width = new_visual_w

                self._draw_horizontal_filenames(
                    app_state,
                    target_image,
                    font,
                    truncated_name1,
                    truncated_name2,
                    split_position_on_canvas,
                    line_thickness,
                    margin,
                    image_rect_on_canvas,
                    app_state.file_name_color.getRgb(),
                    app_state.file_name_bg_color.getRgb(),
                    app_state.font_weight,
                    w1,
                    w2
                )
        except Exception as e:
            traceback.print_exc()
