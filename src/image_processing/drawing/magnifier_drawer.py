
import logging
import math
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageOps
from PyQt6.QtCore import QPoint

from core.app_state import AppState
from core.constants import AppConstants
from image_processing.analysis import (
    create_highlight_diff,
    create_grayscale_diff,
    create_ssim_map,
    create_edge_map
)
from image_processing.resize import resample_image, resample_image_subpixel
from utils.resource_loader import resource_path

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
        self.composer = None

    def _create_diff_image(self, image1: Image.Image, image2: Image.Image | None, mode: str = 'highlight', threshold: int = 20) -> Image.Image | None:
        try:
            font_path = self.composer.font_path if hasattr(self, 'composer') and self.composer else None

            if mode == 'edges':
                if not image1:
                    return None
                return create_edge_map(image1)

            if not image1 or image2 is None:
                return None

            if image1.size != image2.size:
                try:
                    image2 = image2.resize(image1.size, Image.Resampling.LANCZOS)
                except Exception:
                    return None

            if mode == 'ssim':
                return create_ssim_map(image1, image2, font_path)
            elif mode == 'grayscale':
                return create_grayscale_diff(image1, image2, font_path)
            else:
                return create_highlight_diff(image1, image2, threshold, font_path)
        except Exception:
            return None

    def get_smooth_circular_mask(self, size: int) -> Image.Image | None:
        return get_smooth_circular_mask(size)
    def _should_use_subpixel(self, crop_box1: tuple, crop_box2: tuple) -> bool:
        try:
            size1 = abs((crop_box1[2] - crop_box1[0]) * (crop_box1[3] - crop_box1[1]))
            size2 = abs((crop_box2[2] - crop_box2[0]) * (crop_box2[3] - crop_box2[1]))
            if min(size1, size2) <= 0:
                return False
            ratio = max(size1, size2) / min(size1, size2)
            return ratio > 1.1
        except Exception:
            return False

    def _compute_crop_boxes_subpixel(self, image1: Image.Image, image2: Image.Image,
                                     app_state: AppState) -> tuple[tuple[float, float, float, float],
                                                                   tuple[float, float, float, float]]:
        """Вычисляет субпиксельные координаты для crop областей."""
        try:
            w1, h1 = image1.size
            w2, h2 = image2.size

            ref_dim = min(w1, h1)
            thickness_display = max(int(MIN_CAPTURE_THICKNESS), int(round(ref_dim * 0.003)))
            capture_size_px = max(1, int(round(app_state.capture_size_relative * min(w1, h1))))
            inner_size = max(1, capture_size_px - thickness_display)

            if inner_size % 2 != 0:
                inner_size += 1

            cx1 = app_state.capture_position_relative.x() * w1
            cy1 = app_state.capture_position_relative.y() * h1
            left1 = cx1 - inner_size / 2.0
            top1 = cy1 - inner_size / 2.0
            right1 = left1 + inner_size
            bottom1 = top1 + inner_size

            left1 = max(0, left1); top1 = max(0, top1)
            right1 = min(w1, right1); bottom1 = min(h1, bottom1)

            cx2 = app_state.capture_position_relative.x() * w2
            cy2 = app_state.capture_position_relative.y() * h2
            left2 = cx2 - inner_size / 2.0
            top2 = cy2 - inner_size / 2.0
            right2 = left2 + inner_size

            left2 = max(0, left2); top2 = max(0, top2)
            right2 = min(w2, right2); bottom2 = min(h2, bottom2)

            return (left1, top1, right1, bottom1), (left2, top2, right2, bottom2)
        except Exception:

            return ((0.0, 0.0, 1.0, 1.0), (0.0, 0.0, 1.0, 1.0))

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

    def draw_magnifier(
        self,
        draw: ImageDraw.ImageDraw,
        app_state: AppState,
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
        internal_split: float = 0.5,
        divider_visible: bool = True,
        divider_color: tuple = (255, 255, 255, 230),
        divider_thickness: int = 2,
    ):
        """
        Диспетчер стратегий рисования лупы.
        4 стратегии:
        - 2 отдельные лупы
        - 1 соединенная лупа
        - 3 лупы (две оригинала + дифф по центру)
        - 1 лупа сверху и 1 соединенная снизу (ориентируется по app_state.is_horizontal)
        """
        if not all([image1_for_crop, image2_for_crop, crop_box1, crop_box2, magnifier_midpoint_target]) or magnifier_size_pixels <= 0:
            return
        if image_to_draw_on.mode != "RGBA":
            try:
                image_to_draw_on = image_to_draw_on.convert("RGBA")
            except Exception:
                return

        show_left = getattr(app_state, "magnifier_visible_left", True)
        show_center = getattr(app_state, "magnifier_visible_center", True)
        show_right = getattr(app_state, "magnifier_visible_right", True)

        spacing_threshold = AppConstants.MIN_MAGNIFIER_SPACING_RELATIVE_FOR_COMBINE
        should_combine_under_diff = app_state.magnifier_spacing_relative_visual < spacing_threshold
        if hasattr(app_state, 'magnifier_combine_under_diff'):
            app_state.magnifier_combine_under_diff = should_combine_under_diff

        diff_mode = app_state.diff_mode
        is_visual_diff = diff_mode in ('highlight', 'grayscale', 'ssim', 'edges')

        effective_force_combine = bool(force_combine and show_left and show_right)

        try:
            if is_visual_diff and not should_combine_under_diff:
                if not show_center:

                    self._draw_strategy_two_magnifiers(
                        image_to_draw_on=image_to_draw_on,
                        image1_for_crop=image1_for_crop, image2_for_crop=image2_for_crop,
                        crop_box1=crop_box1, crop_box2=crop_box2,
                        midpoint=magnifier_midpoint_target,
                        magnifier_size=magnifier_size_pixels,
                        spacing=edge_spacing_pixels,
                        interpolation_method=interpolation_method,
                        is_interactive=is_interactive_render,
                        layout_horizontal=app_state.is_horizontal,
                        app_state=app_state,
                        show_left=show_left,
                        show_right=show_right,
                    )
                else:

                    self._draw_strategy_three_magnifiers(
                        image_to_draw_on=image_to_draw_on,
                        image1_for_crop=image1_for_crop, image2_for_crop=image2_for_crop,
                        crop_box1=crop_box1, crop_box2=crop_box2,
                        midpoint=magnifier_midpoint_target,
                        magnifier_size=magnifier_size_pixels,
                        spacing=edge_spacing_pixels,
                        interpolation_method=interpolation_method,
                        is_interactive=is_interactive_render,
                        diff_mode=diff_mode,
                        layout_horizontal=app_state.is_horizontal,
                        app_state=app_state,
                        show_left=show_left,
                        show_center=show_center,
                        show_right=show_right,
                    )
            elif is_visual_diff and should_combine_under_diff:
                if not show_center:

                    if show_left and show_right:
                        self._draw_strategy_combined_single(
                            image_to_draw_on=image_to_draw_on,
                            image1_for_crop=image1_for_crop, image2_for_crop=image2_for_crop,
                            crop_box1=crop_box1, crop_box2=crop_box2,
                            midpoint=magnifier_midpoint_target,
                            magnifier_size=magnifier_size_pixels,
                            interpolation_method=interpolation_method,
                            is_interactive=is_interactive_render,
                            is_horizontal=app_state.magnifier_is_horizontal,
                            internal_split=app_state.magnifier_internal_split,
                            divider_visible=app_state.magnifier_divider_visible,
                            divider_color=divider_color,
                            divider_thickness=app_state.magnifier_divider_thickness,
                            app_state=app_state
                        )
                    else:

                        self._draw_strategy_two_magnifiers(
                            image_to_draw_on=image_to_draw_on,
                            image1_for_crop=image1_for_crop, image2_for_crop=image2_for_crop,
                            crop_box1=crop_box1, crop_box2=crop_box2,
                            midpoint=magnifier_midpoint_target,
                            magnifier_size=magnifier_size_pixels,
                            spacing=edge_spacing_pixels,
                            interpolation_method=interpolation_method,
                            is_interactive=is_interactive_render,
                            layout_horizontal=app_state.magnifier_is_horizontal,
                            app_state=app_state,
                            show_left=show_left,
                            show_right=show_right,
                        )
                else:

                    if show_left and show_right:
                        self._draw_strategy_diff_top_combined_bottom(
                            image_to_draw_on=image_to_draw_on,
                            image1_for_crop=image1_for_crop, image2_for_crop=image2_for_crop,
                            crop_box1=crop_box1, crop_box2=crop_box2,
                            midpoint=magnifier_midpoint_target,
                            magnifier_size=magnifier_size_pixels,
                            interpolation_method=interpolation_method,
                            is_interactive=is_interactive_render,
                            diff_mode=diff_mode,
                            comb_is_horizontal=app_state.magnifier_is_horizontal,
                            comb_split=app_state.magnifier_internal_split,
                            comb_divider_visible=app_state.magnifier_divider_visible,
                            comb_divider_color=divider_color,
                            comb_divider_thickness=app_state.magnifier_divider_thickness,
                            layout_horizontal=app_state.is_horizontal,
                            app_state=app_state,
                            show_center=show_center,
                            show_left=show_left,
                            show_right=show_right,
                        )
                    else:
                        self._draw_strategy_three_magnifiers(
                            image_to_draw_on=image_to_draw_on,
                            image1_for_crop=image1_for_crop, image2_for_crop=image2_for_crop,
                            crop_box1=crop_box1, crop_box2=crop_box2,
                            midpoint=magnifier_midpoint_target,
                            magnifier_size=magnifier_size_pixels,
                            spacing=edge_spacing_pixels,
                            interpolation_method=interpolation_method,
                            is_interactive=is_interactive_render,
                            diff_mode=diff_mode,
                            layout_horizontal=app_state.is_horizontal,
                            app_state=app_state,
                            show_left=show_left,
                            show_center=show_center,
                            show_right=show_right,
                        )
            elif effective_force_combine:

                self._draw_strategy_combined_single(
                    image_to_draw_on=image_to_draw_on,
                    image1_for_crop=image1_for_crop, image2_for_crop=image2_for_crop,
                    crop_box1=crop_box1, crop_box2=crop_box2,
                    midpoint=magnifier_midpoint_target,
                    magnifier_size=magnifier_size_pixels,
                    interpolation_method=interpolation_method,
                    is_interactive=is_interactive_render,
                    is_horizontal=app_state.magnifier_is_horizontal,
                    internal_split=app_state.magnifier_internal_split,
                    divider_visible=app_state.magnifier_divider_visible,
                    divider_color=divider_color,
                    divider_thickness=app_state.magnifier_divider_thickness,
                    app_state=app_state
                )
            else:

                self._draw_strategy_two_magnifiers(
                    image_to_draw_on=image_to_draw_on,
                    image1_for_crop=image1_for_crop, image2_for_crop=image2_for_crop,
                    crop_box1=crop_box1, crop_box2=crop_box2,
                    midpoint=magnifier_midpoint_target,
                    magnifier_size=magnifier_size_pixels,
                    spacing=edge_spacing_pixels,
                    interpolation_method=interpolation_method,
                    is_interactive=is_interactive_render,
                    layout_horizontal=app_state.magnifier_is_horizontal,
                    app_state=app_state,
                    show_left=show_left,
                    show_right=show_right,
                )
        except Exception:
            pass

    def _draw_strategy_three_magnifiers(
        self,
        image_to_draw_on: Image.Image,
        image1_for_crop: Image.Image,
        image2_for_crop: Image.Image,
        crop_box1: tuple,
        crop_box2: tuple,
        midpoint: QPoint,
        magnifier_size: int,
        spacing: int,
        interpolation_method: str,
        is_interactive: bool,
        diff_mode: str,
        layout_horizontal: bool,
        app_state: AppState,
        show_left: bool = True,
        show_center: bool = True,
        show_right: bool = True,
    ):
        """3 лупы: по бокам оригиналы, по центру дифф/edges (учет видимости)."""
        try:
            app_state.is_magnifier_combined = False
        except Exception:
            pass

        spacing_f = float(spacing)
        mid_x, mid_y = midpoint.x(), midpoint.y()

        offset = max(magnifier_size, magnifier_size + spacing_f)

        if not layout_horizontal:
            center_left = QPoint(int(round(mid_x - offset)), int(round(mid_y)))
            center_right = QPoint(int(round(mid_x + offset)), int(round(mid_y)))
        else:
            center_left = QPoint(int(round(mid_x)), int(round(mid_y - offset)))
            center_right = QPoint(int(round(mid_x)), int(round(mid_y + offset)))

        try:
            cropped1 = image1_for_crop.crop(crop_box1)
            cropped2 = image2_for_crop.crop(crop_box2)

            if show_left:
                self.draw_single_magnifier_circle(
                    target_image=image_to_draw_on, display_center_pos=center_left,
                    crop_box_orig=None, magnifier_size_pixels=magnifier_size,
                    image_for_crop=cropped1, interpolation_method=interpolation_method,
                    is_interactive_render=is_interactive
                )
            if show_right:
                self.draw_single_magnifier_circle(
                    target_image=image_to_draw_on, display_center_pos=center_right,
                    crop_box_orig=None, magnifier_size_pixels=magnifier_size,
                    image_for_crop=cropped2, interpolation_method=interpolation_method,
                    is_interactive_render=is_interactive
                )

            diff_center_patch = None
            if show_center:
                try:
                    precomputed = getattr(self.composer, 'precomputed_center_diff_display', None)
                except Exception:
                    precomputed = None

                if isinstance(precomputed, Image.Image):
                    w, h = precomputed.size
                    ref_dim = min(w, h)
                    thickness_display = max(int(MIN_CAPTURE_THICKNESS), int(round(ref_dim * 0.003)))
                    capture_size_px = max(1, int(round(app_state.capture_size_relative * min(w, h))))
                    inner_size = max(1, capture_size_px - thickness_display)
                    if inner_size % 2 != 0:
                        inner_size += 1
                    cx = app_state.capture_position_relative.x() * w
                    cy = app_state.capture_position_relative.y() * h
                    left = int(round(cx - inner_size / 2.0)); top = int(round(cy - inner_size / 2.0))
                    right = left + inner_size; bottom = top + inner_size
                    left = max(0, left); top = max(0, top)
                    right = min(w, right); bottom = min(h, bottom)
                    crop_box_display = (left, top, right, bottom)
                    try:
                        diff_center_patch = precomputed.crop(crop_box_display)
                    except Exception:
                        diff_center_patch = None

                if diff_center_patch is None:
                    if diff_mode == 'edges':
                        diff_center_patch = self._create_diff_image(cropped1, None, mode='edges')
                    else:
                        diff_center_patch = self._create_diff_image(cropped1, cropped2, mode=diff_mode)

                if isinstance(diff_center_patch, Image.Image):
                    self.draw_single_magnifier_circle(
                        target_image=image_to_draw_on, display_center_pos=midpoint,
                        crop_box_orig=None, magnifier_size_pixels=magnifier_size,
                        image_for_crop=diff_center_patch, interpolation_method=interpolation_method,
                        is_interactive_render=False
                    )
        except Exception:
            pass

    def _draw_strategy_diff_top_combined_bottom(
        self,
        image_to_draw_on: Image.Image,
        image1_for_crop: Image.Image,
        image2_for_crop: Image.Image,
        crop_box1: tuple,
        crop_box2: tuple,
        midpoint: QPoint,
        magnifier_size: int,
        interpolation_method: str,
        is_interactive: bool,
        diff_mode: str,
        comb_is_horizontal: bool,
        comb_split: float,
        comb_divider_visible: bool,
        comb_divider_color: tuple,
        comb_divider_thickness: int,
        layout_horizontal: bool,
        app_state: AppState,
        show_center: bool = True,
        show_left: bool = True,
        show_right: bool = True,
    ):
        """1 дифф‑лупа сверху и 1 соединенная снизу (или слева/справа при горизонтальном макете), учет видимости."""
        try:
            diff_patch = None
            try:
                precomputed = getattr(self.composer, 'precomputed_center_diff_display', None)
            except Exception:
                precomputed = None

            if isinstance(precomputed, Image.Image):
                w, h = precomputed.size
                ref_dim = min(w, h)
                thickness_display = max(int(MIN_CAPTURE_THICKNESS), int(round(ref_dim * 0.003)))
                capture_size_px = max(1, int(round(app_state.capture_size_relative * min(w, h))))
                inner_size = max(1, capture_size_px - thickness_display)
                if inner_size % 2 != 0:
                    inner_size += 1
                cx = app_state.capture_position_relative.x() * w
                cy = app_state.capture_position_relative.y() * h
                left = int(round(cx - inner_size / 2.0)); top = int(round(cy - inner_size / 2.0))
                right = left + inner_size; bottom = top + inner_size
                left = max(0, left); top = max(0, top)
                right = min(w, right); bottom = min(h, bottom)
                crop_box_display = (left, top, right, bottom)
                try:
                    diff_patch = precomputed.crop(crop_box_display)
                except Exception:
                    diff_patch = None

            if diff_patch is None:
                cropped1 = image1_for_crop.crop(crop_box1)
                cropped2 = image2_for_crop.crop(crop_box2)
                diff_patch = self._create_diff_image(cropped1, cropped2, mode=diff_mode)

            if show_center and isinstance(diff_patch, Image.Image):
                self.draw_single_magnifier_circle(
                    target_image=image_to_draw_on, display_center_pos=midpoint,
                    crop_box_orig=None, magnifier_size_pixels=magnifier_size,
                    image_for_crop=diff_patch, interpolation_method=interpolation_method,
                    is_interactive_render=False
                )

            if show_left and show_right:
                mid_x, mid_y = midpoint.x(), midpoint.y()
                if not layout_horizontal:
                    combined_pos = QPoint(int(round(mid_x)), int(round(mid_y + magnifier_size + 8)))
                else:
                    combined_pos = QPoint(int(round(mid_x + magnifier_size + 8)), int(round(mid_y)))

                try:
                    app_state.is_magnifier_combined = True
                    app_state.magnifier_screen_center = combined_pos
                    app_state.magnifier_screen_size = magnifier_size
                except Exception:
                    pass

                self.draw_combined_magnifier_circle(
                    target_image=image_to_draw_on, display_center_pos=combined_pos,
                    crop_box1=crop_box1, crop_box2=crop_box2,
                    magnifier_size_pixels=magnifier_size,
                    image1_for_crop=image1_for_crop, image2_for_crop=image2_for_crop,
                    interpolation_method=interpolation_method, is_horizontal=comb_is_horizontal,
                    is_interactive_render=is_interactive,
                    internal_split=comb_split,
                    divider_visible=comb_divider_visible,
                    divider_color=comb_divider_color,
                    divider_thickness=comb_divider_thickness,
                )
        except Exception:
            pass

    def _draw_strategy_two_magnifiers(
        self,
        image_to_draw_on: Image.Image,
        image1_for_crop: Image.Image,
        image2_for_crop: Image.Image,
        crop_box1: tuple,
        crop_box2: tuple,
        midpoint: QPoint,
        magnifier_size: int,
        spacing: int,
        interpolation_method: str,
        is_interactive: bool,
        layout_horizontal: bool,
        app_state: AppState,
        show_left: bool = True,
        show_right: bool = True,
    ):
        """2 отдельные лупы по разные стороны от центральной точки (учет видимости)."""
        try:
            try:
                app_state.is_magnifier_combined = False
            except Exception:
                pass
            radius = float(magnifier_size) / 2.0
            half_spacing = float(spacing) / 2.0
            offset_from_midpoint = radius + half_spacing
            mid_x, mid_y = midpoint.x(), midpoint.y()

            if not layout_horizontal:
                center1 = QPoint(int(round(mid_x - offset_from_midpoint)), int(round(mid_y)))
                center2 = QPoint(int(round(mid_x + offset_from_midpoint)), int(round(mid_y)))
            else:
                center1 = QPoint(int(round(mid_x)), int(round(mid_y - offset_from_midpoint)))
                center2 = QPoint(int(round(mid_x)), int(round(mid_y + offset_from_midpoint)))

            if show_left and show_right:

                self.draw_single_magnifier_circle(
                    target_image=image_to_draw_on, display_center_pos=center1,
                    crop_box_orig=crop_box1, magnifier_size_pixels=magnifier_size,
                    image_for_crop=image1_for_crop, interpolation_method=interpolation_method,
                    is_interactive_render=is_interactive
                )
                self.draw_single_magnifier_circle(
                    target_image=image_to_draw_on, display_center_pos=center2,
                    crop_box_orig=crop_box2, magnifier_size_pixels=magnifier_size,
                    image_for_crop=image2_for_crop, interpolation_method=interpolation_method,
                    is_interactive_render=is_interactive
                )
            elif show_left and not show_right:

                self.draw_single_magnifier_circle(
                    target_image=image_to_draw_on, display_center_pos=midpoint,
                    crop_box_orig=crop_box1, magnifier_size_pixels=magnifier_size,
                    image_for_crop=image1_for_crop, interpolation_method=interpolation_method,
                    is_interactive_render=is_interactive
                )
            elif show_right and not show_left:
                self.draw_single_magnifier_circle(
                    target_image=image_to_draw_on, display_center_pos=midpoint,
                    crop_box_orig=crop_box2, magnifier_size_pixels=magnifier_size,
                    image_for_crop=image2_for_crop, interpolation_method=interpolation_method,
                    is_interactive_render=is_interactive
                )
            else:

                return
        except Exception:
            pass

    def _draw_strategy_combined_single(
        self,
        image_to_draw_on: Image.Image,
        image1_for_crop: Image.Image,
        image2_for_crop: Image.Image,
        crop_box1: tuple,
        crop_box2: tuple,
        midpoint: QPoint,
        magnifier_size: int,
        interpolation_method: str,
        is_interactive: bool,
        is_horizontal: bool,
        internal_split: float,
        divider_visible: bool,
        divider_color: tuple,
        divider_thickness: int,
        app_state: AppState,
    ):
        """1 соединенная лупа в центре."""
        try:
            try:
                app_state.is_magnifier_combined = True
                app_state.magnifier_screen_center = midpoint
                app_state.magnifier_screen_size = magnifier_size
            except Exception:
                pass
            self.draw_combined_magnifier_circle(
                target_image=image_to_draw_on, display_center_pos=midpoint,
                crop_box1=crop_box1, crop_box2=crop_box2,
                magnifier_size_pixels=magnifier_size,
                image1_for_crop=image1_for_crop, image2_for_crop=image2_for_crop,
                interpolation_method=interpolation_method, is_horizontal=is_horizontal,
                is_interactive_render=is_interactive, internal_split=internal_split,
                divider_visible=divider_visible, divider_color=divider_color,
                divider_thickness=divider_thickness,
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
        internal_split: float = 0.5,
        divider_visible: bool = True,
        divider_color: tuple = (255, 255, 255, 230),
        divider_thickness: int = 2,
    ):
        if not all([image1_for_crop, image2_for_crop, crop_box1, crop_box2, magnifier_size_pixels > 0]):
            return

        try:
            border_width = max(2, int(magnifier_size_pixels * 0.015))
            content_size = magnifier_size_pixels - border_width * 2 + 2
            if content_size <= 0:
                return

            diff_mode_active = self.composer.app_state.diff_mode != 'off' if hasattr(self.composer, 'app_state') else False

            if self._should_use_subpixel(crop_box1, crop_box2):

                crop_box1_float = crop_box1 if isinstance(crop_box1, tuple) and len(crop_box1) == 4 and isinstance(crop_box1[0], float) else (float(crop_box1[0]), float(crop_box1[1]), float(crop_box1[2]), float(crop_box1[3]))
                crop_box2_float = crop_box2 if isinstance(crop_box2, tuple) and len(crop_box2) == 4 and isinstance(crop_box2[0], float) else (float(crop_box2[0]), float(crop_box2[1]), float(crop_box2[2]), float(crop_box2[3]))
                scaled_content1 = resample_image_subpixel(image1_for_crop, crop_box1_float, (content_size, content_size), interpolation_method, is_interactive_render, diff_mode_active)
                scaled_content2 = resample_image_subpixel(image2_for_crop, crop_box2_float, (content_size, content_size), interpolation_method, is_interactive_render, diff_mode_active)
            else:

                cropped1 = image1_for_crop.crop(crop_box1)
                cropped2 = image2_for_crop.crop(crop_box2)
                scaled_content1 = resample_image(cropped1, (content_size, content_size), interpolation_method, is_interactive_render, diff_mode_active=diff_mode_active)
                scaled_content2 = resample_image(cropped2, (content_size, content_size), interpolation_method, is_interactive_render, diff_mode_active=diff_mode_active)

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

                split_content_x = int(content_size * internal_split)
                left_half = scaled_content1.crop((0, 0, split_content_x, content_size))
                right_half = scaled_content2.crop((split_content_x, 0, content_size, content_size))
                final_magnifier_widget.paste(left_half, (content_paste_pos, content_paste_pos), mask=left_half)
                final_magnifier_widget.paste(right_half, (content_paste_pos + split_content_x, content_paste_pos), mask=right_half)

                if divider_visible:
                    line_thickness = max(1, divider_thickness)

                    split_line_x = content_paste_pos + split_content_x
                    line_image = Image.new("RGBA", (magnifier_size_pixels, magnifier_size_pixels), (0,0,0,0))
                    ImageDraw.Draw(line_image).rectangle((split_line_x - line_thickness // 2, 0, split_line_x + (line_thickness + 1) // 2 - 1, magnifier_size_pixels), fill=divider_color)
                else:
                    line_image = None
            else:

                split_content_y = int(content_size * internal_split)
                top_half = scaled_content1.crop((0, 0, content_size, split_content_y))
                bottom_half = scaled_content2.crop((0, split_content_y, content_size, content_size))
                final_magnifier_widget.paste(top_half, (content_paste_pos, content_paste_pos), mask=top_half)
                final_magnifier_widget.paste(bottom_half, (content_paste_pos, content_paste_pos + split_content_y), mask=bottom_half)

                if divider_visible:
                    line_thickness = max(1, divider_thickness)

                    split_line_y = content_paste_pos + split_content_y
                    line_image = Image.new("RGBA", (magnifier_size_pixels, magnifier_size_pixels), (0,0,0,0))
                    ImageDraw.Draw(line_image).rectangle((0, split_line_y - line_thickness // 2, magnifier_size_pixels, split_line_y + (line_thickness + 1) // 2 - 1), fill=divider_color)
                else:
                    line_image = None

            if line_image:
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
        if not isinstance(image_for_crop, Image.Image) or magnifier_size_pixels <= 0:
            return

        if crop_box_orig is not None and self._should_use_subpixel(crop_box_orig, crop_box_orig):
            crop_box_float = crop_box_orig if isinstance(crop_box_orig, tuple) and len(crop_box_orig) == 4 and isinstance(crop_box_orig[0], float) else (float(crop_box_orig[0]), float(crop_box_orig[1]), float(crop_box_orig[2]), float(crop_box_orig[3]))
            cropped = None
        else:
            cropped = image_for_crop if crop_box_orig is None else image_for_crop.crop(crop_box_orig)

        try:
            border_width = max(2, int(magnifier_size_pixels * 0.015))
            content_size = magnifier_size_pixels - border_width * 2 + 2
            if content_size <= 0:
                return

            diff_mode_active = self.composer.app_state.diff_mode != 'off' if hasattr(self.composer, 'app_state') else False
            if crop_box_orig is not None and self._should_use_subpixel(crop_box_orig, crop_box_orig):
                scaled_content = resample_image_subpixel(image_for_crop, crop_box_float, (content_size, content_size), interpolation_method, is_interactive_render, diff_mode_active)
            else:
                scaled_content = resample_image(cropped, (content_size, content_size), interpolation_method, is_interactive_render, diff_mode_active=diff_mode_active)

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
