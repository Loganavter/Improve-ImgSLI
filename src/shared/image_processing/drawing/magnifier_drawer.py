

import logging
import math
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageOps
from PyQt6.QtCore import QPoint

from core.store import Store
from core.constants import AppConstants
from plugins.analysis.processing import (
    create_highlight_diff,
    create_grayscale_diff,
    create_ssim_map,
    create_edge_map
)
from shared.image_processing.resize import resample_image, resample_image_subpixel
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

    def _create_diff_image(self, image1: Image.Image, image2: Image.Image | None, mode: str = 'highlight', threshold: int = 20, font_path: str | None = None) -> Image.Image | None:
        try:
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

            diff_mode_handlers = {
                'ssim': lambda: create_ssim_map(image1, image2, font_path),
                'grayscale': lambda: create_grayscale_diff(image1, image2, font_path),
            }

            handler = diff_mode_handlers.get(mode)
            if handler:
                return handler()
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
            return ratio > 1.01
        except Exception:
            return False

    def _compute_crop_boxes_subpixel(self, image1: Image.Image, image2: Image.Image,
                                     store: Store) -> tuple[tuple[float, float, float, float],
                                                                   tuple[float, float, float, float]]:

        try:
            w1, h1 = image1.size
            w2, h2 = image2.size

            ref_dim = min(w1, h1)
            thickness_display = max(int(MIN_CAPTURE_THICKNESS), int(round(ref_dim * 0.003)))
            capture_size_px = max(1, int(round(store.viewport.capture_size_relative * min(w1, h1))))
            inner_size = max(1, capture_size_px - thickness_display)

            if inner_size % 2 != 0:
                inner_size += 1

            cx1 = store.viewport.capture_position_relative.x() * w1
            cy1 = store.viewport.capture_position_relative.y() * h1
            left1 = cx1 - inner_size / 2.0
            top1 = cy1 - inner_size / 2.0
            right1 = left1 + inner_size
            bottom1 = top1 + inner_size

            left1 = max(0, left1); top1 = max(0, top1)
            right1 = min(w1, right1); bottom1 = min(h1, bottom1)

            cx2 = store.viewport.capture_position_relative.x() * w2
            cy2 = store.viewport.capture_position_relative.y() * h2
            left2 = cx2 - inner_size / 2.0
            top2 = cy2 - inner_size / 2.0
            right2 = left2 + inner_size

            left2 = max(0, left2); top2 = max(0, top2)
            right2 = min(w2, right2); bottom2 = min(h2, bottom2)

            return (left1, top1, right1, bottom1), (left2, top2, right2, bottom2)
        except Exception:
            return ((0.0, 0.0, 1.0, 1.0), (0.0, 0.0, 1.0, 1.0))

    def _get_normalized_content(self, img: Image.Image, box: tuple, target_size: int,
                                interpolation_method: str, is_interactive: bool) -> Image.Image:
        """
        Извлекает и масштабирует часть изображения до target_size x target_size.
        Использует субпиксельную точность, если необходимо, чтобы избежать мерцания.
        """

        use_subpixel = self._should_use_subpixel(box, box)

        if use_subpixel:

            box_f = tuple(float(x) for x in box)
            return resample_image_subpixel(
                img, box_f, (target_size, target_size),
                interpolation_method, is_interactive, diff_mode_active=True
            )
        else:

            return resample_image(
                img.crop(box), (target_size, target_size),
                interpolation_method, is_interactive, diff_mode_active=True
            )

    def draw_capture_area(self, image_to_draw_on: Image.Image, center_pos: QPoint, size: int, thickness: int | None = None, color: tuple = (255, 50, 100, 230)):

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

        pastel_red_ring = Image.new("RGBA", (outer_size, outer_size), color)

        paste_pos_x = center_pos.x() - outer_size // 2
        paste_pos_y = center_pos.y() - outer_size // 2

        try:
            image_to_draw_on.paste(pastel_red_ring, (paste_pos_x, paste_pos_y), donut_mask)
        except Exception:
            pass

    def draw_magnifier(
        self,
        store: Store,
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

        border_color: tuple = (255, 255, 255, 255),
        capture_ring_color: tuple = (255, 50, 100, 230),

        precomputed_center_diff_display: Image.Image | None = None,
        font_path: str | None = None,
        external_cache: dict = None,
    ) -> QPoint | None:
        """
        Диспетчер стратегий рисования лупы. Возвращает центр интерактивной части (для hit-test).
        """

        if not all([image1_for_crop, image2_for_crop, crop_box1, crop_box2, magnifier_midpoint_target]) or magnifier_size_pixels <= 0:
            return None

        if image_to_draw_on.mode != "RGBA":
            try:
                image_to_draw_on = image_to_draw_on.convert("RGBA")
            except Exception:
                return None

        show_left = getattr(store.viewport, "magnifier_visible_left", True)
        show_center = getattr(store.viewport, "magnifier_visible_center", True)
        show_right = getattr(store.viewport, "magnifier_visible_right", True)

        diff_mode = getattr(store.viewport, "diff_mode", "off")
        is_visual_diff = diff_mode in ('highlight', 'grayscale', 'ssim', 'edges')

        if is_visual_diff:
            show_center = True

        interactive_center = None

        if force_combine:
            if is_visual_diff and show_center:
                interactive_center = self._draw_strategy_diff_top_combined_bottom(
                    image_to_draw_on=image_to_draw_on,
                    image1_for_crop=image1_for_crop, image2_for_crop=image2_for_crop,
                    crop_box1=crop_box1, crop_box2=crop_box2,
                    midpoint=magnifier_midpoint_target,
                    magnifier_size=magnifier_size_pixels,
                    interpolation_method=interpolation_method,
                    is_interactive=is_interactive_render,
                    diff_mode=diff_mode,
                    comb_is_horizontal=store.viewport.magnifier_is_horizontal,
                    comb_split=internal_split,
                    comb_divider_visible=store.viewport.magnifier_divider_visible,
                    comb_divider_color=divider_color,
                    comb_divider_thickness=divider_thickness,
                    layout_horizontal=store.viewport.is_horizontal,
                    store=store,
                    show_center=show_center,
                    show_left=show_left,
                    show_right=show_right,
                    precomputed_center_diff_display=precomputed_center_diff_display,
                    font_path=font_path,
                    border_color=border_color,
                )
            else:
                self._draw_strategy_combined_single(
                    image_to_draw_on=image_to_draw_on,
                    image1_for_crop=image1_for_crop, image2_for_crop=image2_for_crop,
                    crop_box1=crop_box1, crop_box2=crop_box2,
                    midpoint=magnifier_midpoint_target,
                    magnifier_size=magnifier_size_pixels,
                    interpolation_method=interpolation_method,
                    is_interactive=is_interactive_render,
                    is_horizontal=store.viewport.magnifier_is_horizontal,
                    internal_split=internal_split,
                    divider_visible=store.viewport.magnifier_divider_visible,
                    divider_color=divider_color,
                    divider_thickness=divider_thickness,
                    store=store,
                    border_color=border_color,
                    external_cache=external_cache,
                )
                interactive_center = magnifier_midpoint_target
        elif is_visual_diff:
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
                layout_horizontal=store.viewport.is_horizontal,
                store=store,
                show_left=show_left,
                show_center=show_center,
                show_right=show_right,
                precomputed_center_diff_display=precomputed_center_diff_display,
                font_path=font_path,
                border_color=border_color,
            )
            interactive_center = None
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
                layout_horizontal=store.viewport.magnifier_is_horizontal,
                store=store,
                show_left=show_left,
                show_right=show_right,
                border_color=border_color,
            )
            interactive_center = None

        return interactive_center

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
        store: Store,
        show_left: bool = True,
        show_center: bool = True,
        show_right: bool = True,
        precomputed_center_diff_display: Image.Image | None = None,
        font_path: str | None = None,
        border_color: tuple = (255, 255, 255, 255),
    ):
        """3 лупы: по бокам оригиналы, по центру дифф/edges (учет видимости)."""
        try:
            store.viewport.is_magnifier_combined = False
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

            if show_left:
                self.draw_single_magnifier_circle(
                    target_image=image_to_draw_on, display_center_pos=center_left,
                    crop_box_orig=crop_box1, magnifier_size_pixels=magnifier_size,
                    image_for_crop=image1_for_crop, interpolation_method=interpolation_method,
                    is_interactive_render=is_interactive,
                    border_color=border_color
                )
            if show_right:
                self.draw_single_magnifier_circle(
                    target_image=image_to_draw_on, display_center_pos=center_right,
                    crop_box_orig=crop_box2, magnifier_size_pixels=magnifier_size,
                    image_for_crop=image2_for_crop, interpolation_method=interpolation_method,
                    is_interactive_render=is_interactive,
                    border_color=border_color
                )

            diff_center_patch = None
            if show_center:

                cached_map = getattr(store.viewport, 'cached_diff_image', None)

                if cached_map:

                    border_width = max(2, int(magnifier_size * 0.015))
                    content_size = magnifier_size - border_width * 2 + 2
                    if content_size < 1: content_size = 1

                    diff_center_patch = self._get_normalized_content(
                        cached_map, crop_box1, content_size,
                        interpolation_method, is_interactive
                    )

                if diff_center_patch is None:

                    border_width = max(2, int(magnifier_size * 0.015))
                    content_size = magnifier_size - border_width * 2 + 2
                    if content_size < 1: content_size = 1

                    analysis_interp = "BILINEAR"

                    norm1 = self._get_normalized_content(
                        image1_for_crop, crop_box1, content_size,
                        analysis_interp, is_interactive
                    )
                    norm2 = None
                    if diff_mode != 'edges':
                        norm2 = self._get_normalized_content(
                            image2_for_crop, crop_box2, content_size,
                            analysis_interp, is_interactive
                        )

                    if diff_mode == 'edges':
                        diff_center_patch = self._create_diff_image(norm1, None, mode='edges', font_path=font_path)
                    else:
                        diff_center_patch = self._create_diff_image(norm1, norm2, mode=diff_mode, font_path=font_path)

                if isinstance(diff_center_patch, Image.Image):

                    self.draw_single_magnifier_circle(
                        target_image=image_to_draw_on, display_center_pos=midpoint,
                        crop_box_orig=None, magnifier_size_pixels=magnifier_size,
                        image_for_crop=diff_center_patch, interpolation_method=interpolation_method,
                        is_interactive_render=False,
                        border_color=border_color
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
        store: Store,
        show_center: bool = True,
        show_left: bool = True,
        show_right: bool = True,
        precomputed_center_diff_display: Image.Image | None = None,
        font_path: str | None = None,
        border_color: tuple = (255, 255, 255, 255),
    ) -> QPoint | None:
        """1 дифф‑лупа сверху и 1 соединенная снизу..."""
        combined_pos_result = None
        try:
            diff_patch = None

            if diff_patch is None:

                cached_map = getattr(store.viewport, 'cached_diff_image', None)

                if cached_map:

                    border_width = max(2, int(magnifier_size * 0.015))
                    content_size = magnifier_size - border_width * 2 + 2
                    if content_size < 1: content_size = 1

                    diff_patch = self._get_normalized_content(
                        cached_map, crop_box1, content_size,
                        interpolation_method, is_interactive
                    )

                if diff_patch is None:

                    border_width = max(2, int(magnifier_size * 0.015))
                    content_size = magnifier_size - border_width * 2 + 2
                    if content_size < 1: content_size = 1

                    analysis_interp = "BILINEAR"

                    norm1 = self._get_normalized_content(
                        image1_for_crop, crop_box1, content_size,
                        analysis_interp, is_interactive
                    )
                    norm2 = None
                    if diff_mode != 'edges':
                        norm2 = self._get_normalized_content(
                            image2_for_crop, crop_box2, content_size,
                            analysis_interp, is_interactive
                        )

                    if diff_mode == 'edges':
                        diff_patch = self._create_diff_image(norm1, None, mode='edges', font_path=font_path)
                    else:
                        diff_patch = self._create_diff_image(norm1, norm2, mode=diff_mode, font_path=font_path)

            if show_center and isinstance(diff_patch, Image.Image):
                self.draw_single_magnifier_circle(
                    target_image=image_to_draw_on, display_center_pos=midpoint,
                    crop_box_orig=None, magnifier_size_pixels=magnifier_size,
                    image_for_crop=diff_patch, interpolation_method=interpolation_method,
                    is_interactive_render=False,
                    border_color=border_color
                )

            if show_left and show_right:
                mid_x, mid_y = midpoint.x(), midpoint.y()
                if not layout_horizontal:
                    combined_pos = QPoint(int(round(mid_x)), int(round(mid_y + magnifier_size + 8)))
                else:
                    combined_pos = QPoint(int(round(mid_x + magnifier_size + 8)), int(round(mid_y)))

                combined_pos_result = combined_pos

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
                    border_color=border_color
                )
        except Exception:
            pass

        return combined_pos_result

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
        store: Store,
        show_left: bool = True,
        show_right: bool = True,
        border_color: tuple = (255, 255, 255, 255),
    ):
        """2 отдельные лупы по разные стороны от центральной точки (учет видимости)."""
        try:
            try:
                store.viewport.is_magnifier_combined = False
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

            if not (show_left or show_right):
                return

            if show_left and show_right:

                self.draw_single_magnifier_circle(
                    target_image=image_to_draw_on, display_center_pos=center1,
                    crop_box_orig=crop_box1, magnifier_size_pixels=magnifier_size,
                    image_for_crop=image1_for_crop, interpolation_method=interpolation_method,
                    is_interactive_render=is_interactive,
                    border_color=border_color
                )
                self.draw_single_magnifier_circle(
                    target_image=image_to_draw_on, display_center_pos=center2,
                    crop_box_orig=crop_box2, magnifier_size_pixels=magnifier_size,
                    image_for_crop=image2_for_crop, interpolation_method=interpolation_method,
                    is_interactive_render=is_interactive,
                    border_color=border_color
                )
            elif show_left:

                self.draw_single_magnifier_circle(
                    target_image=image_to_draw_on, display_center_pos=midpoint,
                    crop_box_orig=crop_box1, magnifier_size_pixels=magnifier_size,
                    image_for_crop=image1_for_crop, interpolation_method=interpolation_method,
                    is_interactive_render=is_interactive,
                    border_color=border_color
                )
            else:

                self.draw_single_magnifier_circle(
                    target_image=image_to_draw_on, display_center_pos=midpoint,
                    crop_box_orig=crop_box2, magnifier_size_pixels=magnifier_size,
                    image_for_crop=image2_for_crop, interpolation_method=interpolation_method,
                    is_interactive_render=is_interactive,
                    border_color=border_color
                )
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
        store: Store,
        border_color: tuple = (255, 255, 255, 255),
        external_cache: dict = None,
    ):
        """1 соединенная лупа в центре."""
        try:
            self.draw_combined_magnifier_circle(
                target_image=image_to_draw_on, display_center_pos=midpoint,
                crop_box1=crop_box1, crop_box2=crop_box2,
                magnifier_size_pixels=magnifier_size,
                image1_for_crop=image1_for_crop, image2_for_crop=image2_for_crop,
                interpolation_method=interpolation_method, is_horizontal=is_horizontal,
                is_interactive_render=is_interactive, internal_split=internal_split,
                divider_visible=divider_visible, divider_color=divider_color,
                divider_thickness=divider_thickness,
                border_color=border_color,
                external_cache=external_cache
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
        border_color: tuple = (255, 255, 255, 255),
        external_cache: dict = None,
    ):
        if not all([image1_for_crop, image2_for_crop, crop_box1, crop_box2, magnifier_size_pixels > 0]):
            return

        try:
            border_width = max(2, int(magnifier_size_pixels * 0.015))
            content_size = magnifier_size_pixels - border_width * 2 + 2
            if content_size <= 0:
                return

            current_cache_key = (
                crop_box1,
                crop_box2,
                content_size,
                interpolation_method,
                image1_for_crop.size,
                image2_for_crop.size
            )

            scaled1 = None
            scaled2 = None

            if external_cache is not None:
                if "key" in external_cache and external_cache["key"] == current_cache_key:
                    scaled1 = external_cache.get("img1")
                    scaled2 = external_cache.get("img2")

            if scaled1 is None:
                scaled1 = self._get_normalized_content(image1_for_crop, crop_box1, content_size, interpolation_method, is_interactive_render)
                scaled2 = self._get_normalized_content(image2_for_crop, crop_box2, content_size, interpolation_method, is_interactive_render)

                if external_cache is not None:
                    external_cache["key"] = current_cache_key
                    external_cache["img1"] = scaled1
                    external_cache["img2"] = scaled2

            composite = scaled1.copy()

            if not is_horizontal:
                split_x = int(content_size * internal_split)
                if split_x < content_size:
                    part2 = scaled2.crop((split_x, 0, content_size, content_size))
                    composite.paste(part2, (split_x, 0))

                if divider_visible and divider_thickness > 0:
                    draw = ImageDraw.Draw(composite)
                    x0 = split_x - divider_thickness // 2
                    x1 = x0 + divider_thickness
                    draw.rectangle([x0, 0, x1, content_size], fill=divider_color)
            else:
                split_y = int(content_size * internal_split)
                if split_y < content_size:
                    part2 = scaled2.crop((0, split_y, content_size, content_size))
                    composite.paste(part2, (0, split_y))

                if divider_visible and divider_thickness > 0:
                    draw = ImageDraw.Draw(composite)
                    y0 = split_y - divider_thickness // 2
                    y1 = y0 + divider_thickness
                    draw.rectangle([0, y0, content_size, y1], fill=divider_color)

            content_mask = self.get_smooth_circular_mask(content_size)
            if not content_mask: return
            composite.putalpha(content_mask)

            border_mask = self.get_smooth_circular_mask(magnifier_size_pixels)
            if not border_mask: return

            final_magnifier_widget = Image.new("RGBA", (magnifier_size_pixels, magnifier_size_pixels), border_color)
            final_magnifier_widget.putalpha(border_mask)

            paste_offset = border_width - 1
            final_magnifier_widget.paste(composite, (paste_offset, paste_offset), composite)

            paste_x = display_center_pos.x() - (magnifier_size_pixels // 2)
            paste_y = display_center_pos.y() - (magnifier_size_pixels // 2)
            target_image.alpha_composite(final_magnifier_widget, (paste_x, paste_y))

        except Exception as e:
            logger.error(f"Error in draw_combined_magnifier_circle: {e}", exc_info=True)

    def draw_single_magnifier_circle(
        self,
        target_image: Image.Image,
        display_center_pos: QPoint,
        crop_box_orig: tuple | None,
        magnifier_size_pixels: int,
        image_for_crop: Image.Image,
        interpolation_method: str,
        is_interactive_render: bool = False,
        border_color: tuple = (255, 255, 255, 255),
    ):
        if not isinstance(image_for_crop, Image.Image) or magnifier_size_pixels <= 0:
            return

        try:
            border_width = max(2, int(magnifier_size_pixels * 0.015))
            content_size = magnifier_size_pixels - border_width * 2 + 2
            if content_size <= 0:
                return

            if crop_box_orig is not None:

                scaled_content = self._get_normalized_content(image_for_crop, crop_box_orig, content_size, interpolation_method, is_interactive_render)
            else:

                scaled_content = image_for_crop
                if scaled_content.size != (content_size, content_size):
                     scaled_content = scaled_content.resize((content_size, content_size), Image.Resampling.LANCZOS)

            content_mask = self.get_smooth_circular_mask(content_size)
            if not content_mask:
                return
            scaled_content.putalpha(content_mask)

            border_mask = self.get_smooth_circular_mask(magnifier_size_pixels)
            if not border_mask:
                return

            white_fill = Image.new("RGB", (magnifier_size_pixels, magnifier_size_pixels), border_color[:3])

            final_magnifier_widget = Image.new("RGBA", (magnifier_size_pixels, magnifier_size_pixels), (0, 0, 0, 0))
            final_magnifier_widget.paste(white_fill, (0, 0), border_mask)

            content_paste_pos = border_width - 1
            final_magnifier_widget.alpha_composite(scaled_content, (content_paste_pos, content_paste_pos))

            paste_x = display_center_pos.x() - (magnifier_size_pixels // 2)
            paste_y = display_center_pos.y() - (magnifier_size_pixels // 2)
            target_image.alpha_composite(final_magnifier_widget, (paste_x, paste_y))

        except Exception:
            pass
