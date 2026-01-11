import logging
import os
from typing import Callable, Tuple

from PIL import Image, ImageDraw, ImageFont
from PyQt6.QtCore import QRect

from core.store import Store
from utils.resource_loader import truncate_text

logger = logging.getLogger("ImproveImgSLI")

FontType = ImageFont.FreeTypeFont
GetSizeFuncType = Callable[[str, FontType], Tuple[int, int]]

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
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0: return

    if width < radius * 2 or height < radius * 2:
        safe_radius = min(width, height) // 2
        if safe_radius > 0:
            tmp = Image.new("RGBA", (width, height), (0,0,0,0))
            ImageDraw.Draw(tmp).rounded_rectangle((0, 0, width, height), radius=safe_radius, fill=fill)
            target_image.alpha_composite(tmp, (left, top))
        else:

            draw = ImageDraw.Draw(target_image)
            draw.rectangle((left, top, right, bottom), fill=fill)
        return

    template = create_nine_slice_template(radius, fill)
    ts = template.width
    c = radius

    target_image.alpha_composite(template.crop((0, 0, c, c)), (left, top))
    target_image.alpha_composite(template.crop((ts-c, 0, ts, c)), (right-c, top))
    target_image.alpha_composite(template.crop((0, ts-c, c, ts)), (left, bottom-c))
    target_image.alpha_composite(template.crop((ts-c, ts-c, ts, ts)), (right-c, bottom-c))

    if width > 2*c:
        target_image.alpha_composite(template.crop((c, 0, ts-c, c)).resize((width-2*c, c)), (left+c, top))
        target_image.alpha_composite(template.crop((c, ts-c, ts-c, ts)).resize((width-2*c, c)), (left+c, bottom-c))
    if height > 2*c:
        target_image.alpha_composite(template.crop((0, c, c, ts-c)).resize((c, height-2*c)), (left, top+c))
        target_image.alpha_composite(template.crop((ts-c, c, ts, ts-c)).resize((c, height-2*c)), (right-c, top+c))

    if width > 2*c and height > 2*c:
        target_image.alpha_composite(template.crop((c, c, ts-c, ts-c)).resize((width-2*c, height-2*c)), (left+c, top+c))

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

                    default_font = ImageFont.load_default()

                    try:

                        scaled_font = default_font.font_variant(size=size)
                        self._font_cache[cache_key] = scaled_font
                    except (AttributeError, TypeError):

                        self._font_cache[cache_key] = default_font
            except Exception as e:
                logger.warning(f"Failed to load font: {e}")
                default_font = ImageFont.load_default()
                try:
                    self._font_cache[cache_key] = default_font.font_variant(size=size)
                except (AttributeError, TypeError):
                    self._font_cache[cache_key] = default_font
        return self._font_cache[cache_key]

    def _get_cached_text_size(self, text: str, font: FontType, font_weight: int) -> Tuple[int, int]:
        cache_key = (text, font.size, font_weight)
        if cache_key not in self._text_size_cache:

            bbox = font.getbbox(text)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]

            if font_weight > 0:
                stroke_width = int((font.size / 1000.0) * font_weight)
                w += stroke_width * 2
                h += stroke_width * 2

            w += 1
            h += 1

            self._text_size_cache[cache_key] = (w, h)
        return self._text_size_cache[cache_key]

    def _draw_text_with_supersampling_stroke(self, target_image: Image.Image, xy: tuple[int, int], text: str, font: FontType, fill_color: tuple, font_weight: int, alpha_percent: int):
        if not text: return

        base_color = (*fill_color[:3], int((fill_color[3] if len(fill_color)>3 else 255) * alpha_percent / 100))

        if font_weight <= 0:
            draw = ImageDraw.Draw(target_image)

            draw.text(xy, text, fill=base_color, font=font, anchor="lt")
            return

        scale = 4
        hr_font = self._get_cached_font(font.size * scale)
        stroke_w = max(0, int((font.size / 1000.0) * font_weight * scale))

        hr_bbox = hr_font.getbbox(text, stroke_width=stroke_w)
        hr_w = hr_bbox[2] - hr_bbox[0]
        hr_h = hr_bbox[3] - hr_bbox[1]

        if hr_w <= 0 or hr_h <= 0: return

        txt_canvas = Image.new("RGBA", (hr_w, hr_h), (0,0,0,0))
        d = ImageDraw.Draw(txt_canvas)

        d.text((-hr_bbox[0], -hr_bbox[1]), text, fill=base_color, font=hr_font, stroke_width=stroke_w, stroke_fill=base_color)

        final_w = hr_w // scale
        final_h = hr_h // scale
        if final_w > 0 and final_h > 0:
            final_text_img = txt_canvas.resize((final_w, final_h), Image.Resampling.LANCZOS)
            target_image.alpha_composite(final_text_img, (xy[0], xy[1]))

    def draw_filenames_on_image(self, store: Store, target_image: Image.Image, image_rect: QRect, split_pos: int, line_thickness: int, name1: str, name2: str):
        if not store.viewport.include_file_names_in_saved: return

        SAFE_GAP = 5
        PADDING_X = 10
        PADDING_Y = 6

        name_limit = getattr(store.viewport, 'max_name_length', 50)

        rect_w = image_rect.width()
        rect_h = image_rect.height()
        ref_size = min(rect_h, rect_w)

        base_font_ratio = 0.03
        font_size_raw = ref_size * base_font_ratio * (store.viewport.font_size_percent / 100.0)
        font_size = max(20, int(font_size_raw))

        font = self._get_cached_font(font_size, True)
        f_weight = store.viewport.font_weight
        alpha_pc = store.viewport.text_alpha_percent
        half_line = (line_thickness + 1) // 2

        if not store.viewport.is_horizontal:

            w1_avail = (split_pos - image_rect.left()) - half_line - SAFE_GAP

            w2_avail = (image_rect.right() - split_pos) - half_line - SAFE_GAP
        else:
            w1_avail = w2_avail = image_rect.width() - (SAFE_GAP * 2)

        txt1 = truncate_text(name1, int(w1_avail - PADDING_X*2), name_limit, font, lambda t, f: self._get_cached_text_size(t, f, f_weight))
        txt2 = truncate_text(name2, int(w2_avail - PADDING_X*2), name_limit, font, lambda t, f: self._get_cached_text_size(t, f, f_weight))

        th1 = self._get_cached_text_size(txt1, font, f_weight)[1] if txt1 else 0
        th2 = self._get_cached_text_size(txt2, font, f_weight)[1] if txt2 else 0
        current_max_th = max(th1, th2)
        bh = current_max_th + (PADDING_Y * 2)

        t_color = store.viewport.file_name_color.getRgb()
        bg_color_raw = store.viewport.file_name_bg_color.getRgb()
        eff_bg_color = (*bg_color_raw[:3], int(bg_color_raw[3] * alpha_pc / 100))

        def draw_label(display_text, align, slot_num):
            if not display_text: return

            tw, actual_th = self._get_cached_text_size(display_text, font, f_weight)
            bw = tw + (PADDING_X * 2)

            if not store.viewport.is_horizontal:
                by = image_rect.bottom() - SAFE_GAP - bh
            else:
                if slot_num == 1:
                    by = (split_pos - half_line - SAFE_GAP - bh) if store.viewport.text_placement_mode == "split_line" else (image_rect.top() + SAFE_GAP)
                else:
                    by = (split_pos + half_line + SAFE_GAP) if store.viewport.text_placement_mode == "split_line" else (image_rect.bottom() - SAFE_GAP - bh)

            if align == "left_of_split":
                bx = split_pos - half_line - SAFE_GAP - bw
            elif align == "right_of_split":
                bx = split_pos + half_line + SAFE_GAP
            elif align == "left_edge":
                bx = image_rect.left() + SAFE_GAP
            elif align == "right_edge":
                bx = image_rect.right() - SAFE_GAP - bw
            else:
                bx = image_rect.left() + (image_rect.width() - bw) // 2

            final_bx = max(image_rect.left(), min(bx, image_rect.right() - bw))

            final_by = max(image_rect.top(), min(by, image_rect.bottom() - bh))
            bg_rect = [int(final_bx), int(final_by), int(final_bx + bw), int(final_by + bh)]

            if store.viewport.draw_text_background:
                draw_nine_slice_rounded_rect(target_image, bg_rect, 6, eff_bg_color)

            text_x = bg_rect[0] + PADDING_X

            text_y = bg_rect[1] + (bh - actual_th) // 2

            self._draw_text_with_supersampling_stroke(target_image, (text_x, int(text_y)), display_text, font, t_color, f_weight, alpha_pc)

        if not store.viewport.is_horizontal:
            mode1 = "left_of_split" if store.viewport.text_placement_mode == "split_line" else "left_edge"
            mode2 = "right_of_split" if store.viewport.text_placement_mode == "split_line" else "right_edge"
            draw_label(txt1, mode1, 1)
            draw_label(txt2, mode2, 2)
        else:
            draw_label(txt1, "center", 1)
            draw_label(txt2, "center", 2)
