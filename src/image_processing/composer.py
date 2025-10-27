
import logging
import traceback
from typing import Tuple

import numpy as np
from PIL import Image, ImageDraw
from PyQt6.QtCore import QPoint, QRect

from core.app_state import AppState
from core.constants import AppConstants
from image_processing.analysis import (
    create_highlight_diff,
    create_grayscale_diff,
    create_ssim_map,
    create_edge_map,
    extract_channel
)
from image_processing.drawing.magnifier_drawer import (
    MIN_CAPTURE_THICKNESS,
    MagnifierDrawer,
)
from image_processing.drawing.text_drawer import TextDrawer

logger = logging.getLogger("ImproveImgSLI")

class ImageComposer:
    def __init__(self, font_path: str | None):
        self.app_state = None
        self.font_path = font_path

        self.precomputed_center_diff_display: Image.Image | None = None

        if font_path is None or font_path == "":
            self.text_drawer = TextDrawer("")
        else:
            self.text_drawer = TextDrawer(font_path)
            self.magnifier_drawer = MagnifierDrawer()

            self.magnifier_drawer.composer = self

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

    def _extract_channel(self, image: Image.Image, mode: str) -> Image.Image:
        result = extract_channel(image, mode)
        return result if result is not None else image.convert("RGBA")

    def _create_edge_map(self, image: Image.Image) -> Image.Image:
        result = create_edge_map(image)
        return result if result is not None else image.convert("RGBA")

    def generate_comparison_image( # noqa: E121
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
    ) -> Tuple[Image.Image | None, int, int, QRect | None, QPoint | None]: # noqa: E121
        self.app_state = app_state

        if not image1_scaled or not image2_scaled:
            return None, 0, 0, None

        try:
            img_w, img_h = image1_scaled.size

            padding_left, padding_top = 0, 0
            canvas_w, canvas_h = img_w, img_h
            magnifier_bbox_on_canvas = None

            if app_state.use_magnifier and magnifier_drawing_coords:
                magnifier_bbox = magnifier_drawing_coords[-1]
                if magnifier_bbox and not magnifier_bbox.isNull() and magnifier_bbox.isValid():
                    padding_left = abs(min(0, magnifier_bbox.left()))
                    padding_top = abs(min(0, magnifier_bbox.top()))
                    padding_right = max(0, magnifier_bbox.right() - img_w)
                    padding_bottom = max(0, magnifier_bbox.bottom() - img_h)
                    canvas_w = img_w + padding_left + padding_right
                    canvas_h = img_h + padding_top + padding_bottom

                    magnifier_bbox_on_canvas = magnifier_bbox.translated(padding_left, padding_top)

            final_canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
            image_paste_pos = (padding_left, padding_top)

            img1_to_process = self._extract_channel(image1_scaled, app_state.channel_view_mode) if app_state.channel_view_mode != 'RGB' else image1_scaled
            img2_to_process = self._extract_channel(image2_scaled, app_state.channel_view_mode) if app_state.channel_view_mode != 'RGB' else image2_scaled

            if app_state.diff_mode != 'off':

                diff_result = None
                self.precomputed_center_diff_display = None

                cache_key = (
                    app_state.diff_mode,
                    app_state.channel_view_mode,
                    app_state.split_position_visual,
                    app_state.is_horizontal,
                    image1_scaled.size,
                    image2_scaled.size,
                )

                try:
                    cached_base = getattr(app_state, "_cached_split_base_image", None)
                    cached_key = getattr(app_state, "_last_split_cached_params", None)
                    cached_center = getattr(app_state, "_magnifier_cache", {}).get("center_diff_display")
                except Exception:
                    cached_base, cached_key, cached_center = None, None, None

                if cached_base is not None and cached_key == cache_key:
                    base_image_pil = cached_base
                    self.precomputed_center_diff_display = cached_center if isinstance(cached_center, Image.Image) else None
                else:

                    if app_state.diff_mode == 'edges':
                        edge_map1 = self._create_edge_map(img1_to_process)
                        edge_map2 = self._create_edge_map(img2_to_process)
                        if edge_map1 and edge_map2:
                            diff_result = self.create_base_split_image(edge_map1, edge_map2, app_state.split_position_visual, app_state.is_horizontal)
                        self.precomputed_center_diff_display = edge_map1

                    elif app_state.diff_mode == 'highlight':
                        diff_result = create_highlight_diff(img1_to_process, img2_to_process, threshold=10, font_path=self.font_path)
                        self.precomputed_center_diff_display = diff_result

                    elif app_state.diff_mode == 'grayscale':
                        diff_result = create_grayscale_diff(img1_to_process, img2_to_process, font_path=self.font_path)
                        self.precomputed_center_diff_display = diff_result

                    elif app_state.diff_mode == 'ssim':
                        diff_result = create_ssim_map(img1_to_process, img2_to_process, font_path=self.font_path)
                        self.precomputed_center_diff_display = diff_result

                    base_image_pil = diff_result if diff_result else self.create_base_split_image(
                        img1_to_process, img2_to_process, app_state.split_position_visual, app_state.is_horizontal
                    )

                    try:
                        app_state._cached_split_base_image = base_image_pil
                        app_state._last_split_cached_params = cache_key
                        if isinstance(self.precomputed_center_diff_display, Image.Image):
                            if not hasattr(app_state, "_magnifier_cache") or app_state._magnifier_cache is None:
                                app_state._magnifier_cache = {}
                            app_state._magnifier_cache["center_diff_display"] = self.precomputed_center_diff_display
                    except Exception:
                        pass
            else:

                base_image_pil = self.create_base_split_image(
                    img1_to_process, img2_to_process, app_state.split_position_visual, app_state.is_horizontal
                )

                self.precomputed_center_diff_display = None
                try:
                    app_state._cached_split_base_image = None
                    app_state._last_split_cached_params = None
                    if hasattr(app_state, "_magnifier_cache") and isinstance(app_state._magnifier_cache, dict):
                        app_state._magnifier_cache.pop("center_diff_display", None)
                except Exception:
                    pass

            if not base_image_pil:
                return None, 0, 0, None

            final_canvas.paste(base_image_pil, image_paste_pos)

            line_thickness = app_state.divider_line_thickness or 3
            if app_state.divider_line_visible and app_state.diff_mode == 'off':
                line_color_qcolor = app_state.divider_line_color
                line_color = (
                    line_color_qcolor.red(),
                    line_color_qcolor.green(),
                    line_color_qcolor.blue(),
                    line_color_qcolor.alpha()
                )

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
                        fill=line_color,
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
                        fill=line_color,
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

                if magn_mid_on_img is not None:
                    magn_mid_on_canvas = QPoint(magn_mid_on_img.x() + padding_left, magn_mid_on_img.y() + padding_top)

                    both_halves_visible = getattr(app_state, "magnifier_visible_left", True) and getattr(app_state, "magnifier_visible_right", True)
                    should_combine_decision = (app_state.diff_mode != 'off') or (
                        both_halves_visible and (app_state.magnifier_spacing_relative_visual < AppConstants.MIN_MAGNIFIER_SPACING_RELATIVE_FOR_COMBINE)
                    )

                    mag_divider_color = (
                        app_state.magnifier_divider_color.red(),
                        app_state.magnifier_divider_color.green(),
                        app_state.magnifier_divider_color.blue(),
                        app_state.magnifier_divider_color.alpha()
                    )

                    img1_for_crop = original_image1 if original_image1 else image1_scaled
                    img2_for_crop = original_image2 if original_image2 else image2_scaled

                    def _compute_scaled_crop_box(img: Image.Image) -> tuple[int, int, int, int]:
                        w, h = img.size

                        ref_dim = min(img_w, img_h)
                        thickness_display = max(int(MIN_CAPTURE_THICKNESS), int(round(ref_dim * 0.003)))
                        capture_size_px = max(1, int(round(app_state.capture_size_relative * min(w, h))))
                        inner_size = max(1, capture_size_px - thickness_display)

                        if inner_size % 2 != 0:
                            inner_size += 1
                        cx = app_state.capture_position_relative.x() * w
                        cy = app_state.capture_position_relative.y() * h
                        left = int(round(cx - inner_size / 2.0))
                        top = int(round(cy - inner_size / 2.0))
                        right = left + inner_size
                        bottom = top + inner_size

                        left = max(0, left); top = max(0, top)
                        right = min(w, right); bottom = min(h, bottom)
                        return (left, top, right, bottom)

                    def _compute_scaled_crop_box_float(img: Image.Image) -> tuple[float, float, float, float]:
                        w, h = img.size

                        ref_dim = min(img_w, img_h)
                        thickness_display = max(int(MIN_CAPTURE_THICKNESS), int(round(ref_dim * 0.003)))
                        capture_size_px = max(1, int(round(app_state.capture_size_relative * min(w, h))))
                        inner_size = max(1, capture_size_px - thickness_display)

                        if inner_size % 2 != 0:
                            inner_size += 1
                        cx = app_state.capture_position_relative.x() * w
                        cy = app_state.capture_position_relative.y() * h
                        left = cx - inner_size / 2.0
                        top = cy - inner_size / 2.0
                        right = left + inner_size
                        bottom = top + inner_size

                        left = max(0, left); top = max(0, top)
                        right = min(w, right); bottom = min(h, bottom)
                        return (left, top, right, bottom)

                    w1, h1 = img1_for_crop.size
                    w2, h2 = img2_for_crop.size
                    size1_area = w1 * h1
                    size2_area = w2 * h2
                    needs_subpixel = (min(size1_area, size2_area) > 0 and
                                     max(size1_area, size2_area) / min(size1_area, size2_area) > 1.1)

                    if needs_subpixel:

                        crop_box1_used = crop_box1 if original_image1 else _compute_scaled_crop_box_float(img1_for_crop)
                        crop_box2_used = crop_box2 if original_image2 else _compute_scaled_crop_box_float(img2_for_crop)
                    else:

                        crop_box1_used = crop_box1 if original_image1 else _compute_scaled_crop_box(img1_for_crop)
                        crop_box2_used = crop_box2 if original_image2 else _compute_scaled_crop_box(img2_for_crop)

                    effective_interpolation_method = app_state.interpolation_method
                    if app_state.is_interactive_mode and app_state.optimize_magnifier_movement:
                        effective_interpolation_method = app_state.movement_interpolation_method

                    self.magnifier_drawer.draw_magnifier(
                        ImageDraw.Draw(final_canvas),
                        app_state,
                        final_canvas, img1_for_crop, img2_for_crop,
                        crop_box1_used, crop_box2_used, magn_mid_on_canvas, magn_size_pix, magn_spacing_pix,
                        effective_interpolation_method, app_state.magnifier_is_horizontal, should_combine_decision,
                        app_state.is_interactive_mode,
                        app_state.magnifier_internal_split,
                        app_state.magnifier_divider_visible,
                        mag_divider_color,
                        app_state.magnifier_divider_thickness,
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

            both_halves_visible = getattr(app_state, "magnifier_visible_left", True) and getattr(app_state, "magnifier_visible_right", True)
            should_combine_under_diff = (
                app_state.diff_mode != 'off'
                and app_state.magnifier_spacing_relative_visual < AppConstants.MIN_MAGNIFIER_SPACING_RELATIVE_FOR_COMBINE
                and both_halves_visible
            )

            combined_center_if_special_mode = app_state.magnifier_screen_center if should_combine_under_diff else None

            return final_canvas, padding_left, padding_top, magnifier_bbox_on_canvas, combined_center_if_special_mode

        except Exception:
            traceback.print_exc()
            return None, 0, 0, None, None
