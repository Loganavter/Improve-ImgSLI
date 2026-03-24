import logging
import math

from PIL import Image, ImageChops, ImageDraw, ImageOps
from PyQt6.QtCore import QPoint

from core.store import Store
from plugins.analysis.processing import (
    create_edge_map,
    create_grayscale_diff,
    create_highlight_diff,
    create_ssim_map,
)
from shared.image_processing.drawing.magnifier_diff import (
    build_diff_patch,
    build_optional_diff_patch,
    get_magnifier_content_size,
)
from shared.image_processing.drawing.magnifier_layout import (
    compute_axis_pair_centers,
    compute_diff_combined_position,
    compute_three_magnifier_side_centers,
    compute_two_magnifier_centers,
    get_magnifier_sizes,
    set_magnifier_combined_mode,
)
from shared.image_processing.drawing.magnifier_masks import (
    create_framed_magnifier_widget,
    get_smooth_circular_mask,
    paste_magnifier_widget,
)
from shared.image_processing.drawing.magnifier_strategies import (
    draw_diff_combined_bottom_magnifier,
    draw_strategy_combined_single,
    draw_strategy_diff_top_combined_bottom,
    draw_strategy_three_magnifiers,
    draw_strategy_two_magnifiers,
    draw_visible_side_magnifiers,
)
from shared.image_processing.resize import resample_image, resample_image_subpixel

logger = logging.getLogger("ImproveImgSLI")

CAPTURE_THICKNESS_FACTOR = 0.1
MIN_CAPTURE_THICKNESS = 2.0
MAX_CAPTURE_THICKNESS = 8.0

class MagnifierDrawer:
    def __init__(self):
        self._mask_image_cache = None
        self._mask_path_checked = False
        self._resized_mask_cache = {}

    def _create_diff_image(
        self,
        image1: Image.Image,
        image2: Image.Image | None,
        mode: str = "highlight",
        threshold: int = 20,
        font_path: str | None = None,
    ) -> Image.Image | None:
        try:
            if mode == "edges":
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
                "ssim": lambda: create_ssim_map(image1, image2, font_path),
                "grayscale": lambda: create_grayscale_diff(image1, image2, font_path),
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

    def _compute_crop_boxes_subpixel(
        self, image1: Image.Image, image2: Image.Image, store: Store
    ) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float]]:

        try:
            w1, h1 = image1.size
            w2, h2 = image2.size

            ref_dim = min(w1, h1)
            thickness_display = max(
                int(MIN_CAPTURE_THICKNESS), int(round(ref_dim * 0.003))
            )
            capture_size_px = max(
                1, int(round(store.viewport.capture_size_relative * min(w1, h1)))
            )
            inner_size = max(1, capture_size_px - thickness_display)

            if inner_size % 2 != 0:
                inner_size += 1

            cx1 = store.viewport.capture_position_relative.x * w1
            cy1 = store.viewport.capture_position_relative.y * h1
            left1 = cx1 - inner_size / 2.0
            top1 = cy1 - inner_size / 2.0
            right1 = left1 + inner_size
            bottom1 = top1 + inner_size

            left1 = max(0, left1)
            top1 = max(0, top1)
            right1 = min(w1, right1)
            bottom1 = min(h1, bottom1)

            cx2 = store.viewport.capture_position_relative.x * w2
            cy2 = store.viewport.capture_position_relative.y * h2
            left2 = cx2 - inner_size / 2.0
            top2 = cy2 - inner_size / 2.0
            right2 = left2 + inner_size

            left2 = max(0, left2)
            top2 = max(0, top2)
            right2 = min(w2, right2)
            bottom2 = min(h2, bottom2)

            return (left1, top1, right1, bottom1), (left2, top2, right2, bottom2)
        except Exception:
            return ((0.0, 0.0, 1.0, 1.0), (0.0, 0.0, 1.0, 1.0))

    def _get_normalized_content(
        self,
        img: Image.Image,
        box: tuple,
        target_size: int,
        interpolation_method: str,
        is_interactive: bool,
    ) -> Image.Image:
        """
        Извлекает и масштабирует часть изображения до target_size x target_size.
        Использует субпиксельную точность, если необходимо, чтобы избежать мерцания.
        """

        use_subpixel = self._should_use_subpixel(box, box)

        if use_subpixel:

            box_f = tuple(float(x) for x in box)
            return resample_image_subpixel(
                img,
                box_f,
                (target_size, target_size),
                interpolation_method,
                is_interactive,
                diff_mode_active=True,
            )
        else:

            return resample_image(
                img.crop(box),
                (target_size, target_size),
                interpolation_method,
                is_interactive,
                diff_mode_active=True,
            )

    def draw_capture_area(
        self,
        image_to_draw_on: Image.Image,
        center_pos: QPoint,
        size: int,
        thickness: int | None = None,
        color: tuple = (255, 50, 100, 230),
    ):

        if (
            size <= 0
            or center_pos is None
            or not isinstance(image_to_draw_on, Image.Image)
        ):
            return

        try:
            if thickness is None or thickness <= 0:
                thickness_float = CAPTURE_THICKNESS_FACTOR * math.sqrt(
                    max(1.0, float(size))
                )
                thickness_clamped = max(
                    float(MIN_CAPTURE_THICKNESS),
                    min(float(MAX_CAPTURE_THICKNESS), thickness_float),
                )
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
            image_to_draw_on.paste(
                pastel_red_ring, (paste_pos_x, paste_pos_y), donut_mask
            )
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
        if not self._can_draw_magnifier(
            image1_for_crop,
            image2_for_crop,
            crop_box1,
            crop_box2,
            magnifier_midpoint_target,
            magnifier_size_pixels,
        ):
            return None

        context = self._build_magnifier_render_context(
            store=store,
            image_to_draw_on=image_to_draw_on,
            image1_for_crop=image1_for_crop,
            image2_for_crop=image2_for_crop,
            crop_box1=crop_box1,
            crop_box2=crop_box2,
            magnifier_midpoint_target=magnifier_midpoint_target,
            magnifier_size_pixels=magnifier_size_pixels,
            edge_spacing_pixels=edge_spacing_pixels,
            interpolation_method=interpolation_method,
            is_horizontal=is_horizontal,
            force_combine=force_combine,
            is_interactive_render=is_interactive_render,
            internal_split=internal_split,
            divider_visible=divider_visible,
            divider_color=divider_color,
            divider_thickness=divider_thickness,
            border_color=border_color,
            capture_ring_color=capture_ring_color,
            precomputed_center_diff_display=precomputed_center_diff_display,
            font_path=font_path,
            external_cache=external_cache,
        )
        if context is None:
            return None
        return self._dispatch_magnifier_render(context)

    def _can_draw_magnifier(
        self,
        image1_for_crop,
        image2_for_crop,
        crop_box1,
        crop_box2,
        magnifier_midpoint_target,
        magnifier_size_pixels: int,
    ) -> bool:
        return bool(
            all(
                [
                    image1_for_crop,
                    image2_for_crop,
                    crop_box1,
                    crop_box2,
                    magnifier_midpoint_target,
                ]
            )
            and magnifier_size_pixels > 0
        )

    def _ensure_rgba_canvas(self, image_to_draw_on: Image.Image) -> Image.Image | None:
        if image_to_draw_on.mode == "RGBA":
            return image_to_draw_on
        try:
            return image_to_draw_on.convert("RGBA")
        except Exception:
            return None

    def _get_magnifier_visibility(self, store: Store, show_center_required: bool) -> dict:
        show_left = getattr(store.viewport, "magnifier_visible_left", True)
        show_center = getattr(store.viewport, "magnifier_visible_center", True)
        show_right = getattr(store.viewport, "magnifier_visible_right", True)
        diff_mode = getattr(store.viewport, "diff_mode", "off")
        is_visual_diff = diff_mode in ("highlight", "grayscale", "ssim", "edges")
        if show_center_required and is_visual_diff and not show_center:
            is_visual_diff = False
        return {
            "show_left": show_left,
            "show_center": show_center,
            "show_right": show_right,
            "diff_mode": diff_mode,
            "is_visual_diff": is_visual_diff,
        }

    def _draw_combined_magnifier_strategy(self, **kwargs) -> QPoint | None:
        visibility = kwargs.pop("visibility")
        if visibility["is_visual_diff"] and visibility["show_center"]:
            return self._draw_strategy_diff_top_combined_bottom(
                image_to_draw_on=kwargs["image_to_draw_on"],
                image1_for_crop=kwargs["image1_for_crop"],
                image2_for_crop=kwargs["image2_for_crop"],
                crop_box1=kwargs["crop_box1"],
                crop_box2=kwargs["crop_box2"],
                midpoint=kwargs["midpoint"],
                magnifier_size=kwargs["magnifier_size_pixels"],
                interpolation_method=kwargs["interpolation_method"],
                is_interactive=kwargs["is_interactive_render"],
                diff_mode=visibility["diff_mode"],
                comb_is_horizontal=kwargs["store"].viewport.magnifier_is_horizontal,
                comb_split=kwargs["internal_split"],
                comb_divider_visible=kwargs["divider_visible"],
                comb_divider_color=kwargs["divider_color"],
                comb_divider_thickness=kwargs["divider_thickness"],
                layout_horizontal=kwargs["store"].viewport.is_horizontal,
                store=kwargs["store"],
                show_center=visibility["show_center"],
                show_left=visibility["show_left"],
                show_right=visibility["show_right"],
                precomputed_center_diff_display=kwargs["precomputed_center_diff_display"],
                font_path=kwargs["font_path"],
                border_color=kwargs["border_color"],
            )
        self._draw_strategy_combined_single(
            image_to_draw_on=kwargs["image_to_draw_on"],
            image1_for_crop=kwargs["image1_for_crop"],
            image2_for_crop=kwargs["image2_for_crop"],
            crop_box1=kwargs["crop_box1"],
            crop_box2=kwargs["crop_box2"],
            midpoint=kwargs["midpoint"],
            magnifier_size=kwargs["magnifier_size_pixels"],
            interpolation_method=kwargs["interpolation_method"],
            is_interactive=kwargs["is_interactive_render"],
            is_horizontal=kwargs["store"].viewport.magnifier_is_horizontal,
            internal_split=kwargs["internal_split"],
            divider_visible=kwargs["divider_visible"],
            divider_color=kwargs["divider_color"],
            divider_thickness=kwargs["divider_thickness"],
            store=kwargs["store"],
            border_color=kwargs["border_color"],
            external_cache=kwargs["external_cache"],
        )
        return kwargs["midpoint"]

    def _build_magnifier_render_context(self, **kwargs) -> dict | None:
        rgba_canvas = self._ensure_rgba_canvas(kwargs["image_to_draw_on"])
        if rgba_canvas is None:
            return None
        kwargs["image_to_draw_on"] = rgba_canvas
        kwargs["visibility"] = self._get_magnifier_visibility(
            kwargs["store"], show_center_required=True
        )
        return kwargs

    def _dispatch_magnifier_render(self, context: dict) -> QPoint | None:
        if context["force_combine"]:
            return self._draw_combined_magnifier_strategy(**context)
        if context["visibility"]["is_visual_diff"]:
            self._draw_strategy_three_magnifiers(
                image_to_draw_on=context["image_to_draw_on"],
                image1_for_crop=context["image1_for_crop"],
                image2_for_crop=context["image2_for_crop"],
                crop_box1=context["crop_box1"],
                crop_box2=context["crop_box2"],
                midpoint=context["magnifier_midpoint_target"],
                magnifier_size=context["magnifier_size_pixels"],
                spacing=context["edge_spacing_pixels"],
                interpolation_method=context["interpolation_method"],
                is_interactive=context["is_interactive_render"],
                diff_mode=context["visibility"]["diff_mode"],
                layout_horizontal=context["store"].viewport.is_horizontal,
                store=context["store"],
                show_left=context["visibility"]["show_left"],
                show_center=context["visibility"]["show_center"],
                show_right=context["visibility"]["show_right"],
                precomputed_center_diff_display=context["precomputed_center_diff_display"],
                font_path=context["font_path"],
                border_color=context["border_color"],
            )
            return None
        self._draw_strategy_two_magnifiers(
            image_to_draw_on=context["image_to_draw_on"],
            image1_for_crop=context["image1_for_crop"],
            image2_for_crop=context["image2_for_crop"],
            crop_box1=context["crop_box1"],
            crop_box2=context["crop_box2"],
            midpoint=context["magnifier_midpoint_target"],
            magnifier_size=context["magnifier_size_pixels"],
            spacing=context["edge_spacing_pixels"],
            interpolation_method=context["interpolation_method"],
            is_interactive=context["is_interactive_render"],
            layout_horizontal=context["store"].viewport.magnifier_is_horizontal,
            store=context["store"],
            show_left=context["visibility"]["show_left"],
            show_right=context["visibility"]["show_right"],
            border_color=context["border_color"],
        )
        return None

    def _build_diff_patch(
        self,
        *,
        store: Store,
        diff_mode: str,
        magnifier_size: int,
        image1_for_crop: Image.Image,
        image2_for_crop: Image.Image,
        crop_box1: tuple,
        crop_box2: tuple,
        interpolation_method: str,
        is_interactive: bool,
        font_path: str | None = None,
    ) -> Image.Image | None:
        return build_diff_patch(
            self,
            store=store,
            diff_mode=diff_mode,
            magnifier_size=magnifier_size,
            image1_for_crop=image1_for_crop,
            image2_for_crop=image2_for_crop,
            crop_box1=crop_box1,
            crop_box2=crop_box2,
            interpolation_method=interpolation_method,
            is_interactive=is_interactive,
            font_path=font_path,
        )

    def _get_magnifier_content_size(self, magnifier_size: int) -> int:
        return get_magnifier_content_size(magnifier_size)

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
        draw_strategy_three_magnifiers(
            self,
            image_to_draw_on=image_to_draw_on,
            image1_for_crop=image1_for_crop,
            image2_for_crop=image2_for_crop,
            crop_box1=crop_box1,
            crop_box2=crop_box2,
            midpoint=midpoint,
            magnifier_size=magnifier_size,
            spacing=spacing,
            interpolation_method=interpolation_method,
            is_interactive=is_interactive,
            diff_mode=diff_mode,
            layout_horizontal=layout_horizontal,
            store=store,
            show_left=show_left,
            show_center=show_center,
            show_right=show_right,
            precomputed_center_diff_display=precomputed_center_diff_display,
            font_path=font_path,
            border_color=border_color,
        )

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
        return draw_strategy_diff_top_combined_bottom(
            self,
            image_to_draw_on=image_to_draw_on,
            image1_for_crop=image1_for_crop,
            image2_for_crop=image2_for_crop,
            crop_box1=crop_box1,
            crop_box2=crop_box2,
            midpoint=midpoint,
            magnifier_size=magnifier_size,
            interpolation_method=interpolation_method,
            is_interactive=is_interactive,
            diff_mode=diff_mode,
            comb_is_horizontal=comb_is_horizontal,
            comb_split=comb_split,
            comb_divider_visible=comb_divider_visible,
            comb_divider_color=comb_divider_color,
            comb_divider_thickness=comb_divider_thickness,
            layout_horizontal=layout_horizontal,
            store=store,
            show_center=show_center,
            show_left=show_left,
            show_right=show_right,
            precomputed_center_diff_display=precomputed_center_diff_display,
            font_path=font_path,
            border_color=border_color,
        )

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
        draw_strategy_two_magnifiers(
            self,
            image_to_draw_on=image_to_draw_on,
            image1_for_crop=image1_for_crop,
            image2_for_crop=image2_for_crop,
            crop_box1=crop_box1,
            crop_box2=crop_box2,
            midpoint=midpoint,
            magnifier_size=magnifier_size,
            spacing=spacing,
            interpolation_method=interpolation_method,
            is_interactive=is_interactive,
            layout_horizontal=layout_horizontal,
            store=store,
            show_left=show_left,
            show_right=show_right,
            border_color=border_color,
        )

    def _build_optional_diff_patch(
        self,
        *,
        show_center: bool,
        store: Store,
        diff_mode: str,
        magnifier_size: int,
        image1_for_crop: Image.Image,
        image2_for_crop: Image.Image,
        crop_box1: tuple,
        crop_box2: tuple,
        interpolation_method: str,
        is_interactive: bool,
        font_path: str | None,
    ) -> Image.Image | None:
        return build_optional_diff_patch(
            self,
            show_center=show_center,
            store=store,
            diff_mode=diff_mode,
            magnifier_size=magnifier_size,
            image1_for_crop=image1_for_crop,
            image2_for_crop=image2_for_crop,
            crop_box1=crop_box1,
            crop_box2=crop_box2,
            interpolation_method=interpolation_method,
            is_interactive=is_interactive,
            font_path=font_path,
        )

    def _draw_diff_combined_bottom_magnifier(
        self,
        *,
        image_to_draw_on: Image.Image,
        image1_for_crop: Image.Image,
        image2_for_crop: Image.Image,
        crop_box1: tuple,
        crop_box2: tuple,
        midpoint: QPoint,
        magnifier_size: int,
        interpolation_method: str,
        is_interactive: bool,
        comb_is_horizontal: bool,
        comb_split: float,
        comb_divider_visible: bool,
        comb_divider_color: tuple,
        comb_divider_thickness: int,
        layout_horizontal: bool,
        border_color: tuple,
    ) -> QPoint:
        return draw_diff_combined_bottom_magnifier(
            self,
            image_to_draw_on=image_to_draw_on,
            image1_for_crop=image1_for_crop,
            image2_for_crop=image2_for_crop,
            crop_box1=crop_box1,
            crop_box2=crop_box2,
            midpoint=midpoint,
            magnifier_size=magnifier_size,
            interpolation_method=interpolation_method,
            is_interactive=is_interactive,
            comb_is_horizontal=comb_is_horizontal,
            comb_split=comb_split,
            comb_divider_visible=comb_divider_visible,
            comb_divider_color=comb_divider_color,
            comb_divider_thickness=comb_divider_thickness,
            layout_horizontal=layout_horizontal,
            border_color=border_color,
        )

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
        draw_strategy_combined_single(
            self,
            image_to_draw_on=image_to_draw_on,
            image1_for_crop=image1_for_crop,
            image2_for_crop=image2_for_crop,
            crop_box1=crop_box1,
            crop_box2=crop_box2,
            midpoint=midpoint,
            magnifier_size=magnifier_size,
            interpolation_method=interpolation_method,
            is_interactive=is_interactive,
            is_horizontal=is_horizontal,
            internal_split=internal_split,
            divider_visible=divider_visible,
            divider_color=divider_color,
            divider_thickness=divider_thickness,
            store=store,
            border_color=border_color,
            external_cache=external_cache,
        )

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
        if not all(
            [
                image1_for_crop,
                image2_for_crop,
                crop_box1,
                crop_box2,
                magnifier_size_pixels > 0,
            ]
        ):
            return

        try:
            border_width, content_size = self._get_magnifier_sizes(
                magnifier_size_pixels
            )
            if content_size <= 0:
                return

            scaled1, scaled2 = self._get_combined_magnifier_scaled_content(
                crop_box1=crop_box1,
                crop_box2=crop_box2,
                content_size=content_size,
                interpolation_method=interpolation_method,
                image1_for_crop=image1_for_crop,
                image2_for_crop=image2_for_crop,
                is_interactive_render=is_interactive_render,
                external_cache=external_cache,
            )
            if scaled1 is None or scaled2 is None:
                return

            composite = self._build_combined_magnifier_composite(
                scaled1=scaled1,
                scaled2=scaled2,
                content_size=content_size,
                is_horizontal=is_horizontal,
                internal_split=internal_split,
                divider_visible=divider_visible,
                divider_color=divider_color,
                divider_thickness=divider_thickness,
            )
            if composite is None:
                return

            self._paste_magnifier_widget(
                target_image=target_image,
                display_center_pos=display_center_pos,
                magnifier_widget=self._create_framed_magnifier_widget(
                    composite=composite,
                    magnifier_size_pixels=magnifier_size_pixels,
                    border_width=border_width,
                    border_color=border_color,
                ),
            )

        except Exception as e:
            logger.error(f"Error in draw_combined_magnifier_circle: {e}", exc_info=True)

    def _set_magnifier_combined_mode(self, store: Store, combined: bool):
        set_magnifier_combined_mode(store, combined)

    def _compute_three_magnifier_side_centers(
        self,
        *,
        midpoint: QPoint,
        magnifier_size: int,
        spacing: int,
        layout_horizontal: bool,
    ) -> tuple[QPoint, QPoint]:
        return compute_three_magnifier_side_centers(
            midpoint=midpoint,
            magnifier_size=magnifier_size,
            spacing=spacing,
            layout_horizontal=layout_horizontal,
        )

    def _compute_two_magnifier_centers(
        self,
        *,
        midpoint: QPoint,
        magnifier_size: int,
        spacing: int,
        layout_horizontal: bool,
    ) -> tuple[QPoint, QPoint]:
        return compute_two_magnifier_centers(
            midpoint=midpoint,
            magnifier_size=magnifier_size,
            spacing=spacing,
            layout_horizontal=layout_horizontal,
        )

    def _compute_axis_pair_centers(
        self, midpoint: QPoint, offset: float, layout_horizontal: bool
    ) -> tuple[QPoint, QPoint]:
        return compute_axis_pair_centers(midpoint, offset, layout_horizontal)

    def _draw_visible_side_magnifiers(
        self,
        *,
        image_to_draw_on: Image.Image,
        center_left: QPoint,
        center_right: QPoint,
        crop_box1: tuple,
        crop_box2: tuple,
        magnifier_size: int,
        image1_for_crop: Image.Image,
        image2_for_crop: Image.Image,
        interpolation_method: str,
        is_interactive: bool,
        show_left: bool,
        show_right: bool,
        border_color: tuple,
    ):
        draw_visible_side_magnifiers(
            self,
            image_to_draw_on=image_to_draw_on,
            center_left=center_left,
            center_right=center_right,
            crop_box1=crop_box1,
            crop_box2=crop_box2,
            magnifier_size=magnifier_size,
            image1_for_crop=image1_for_crop,
            image2_for_crop=image2_for_crop,
            interpolation_method=interpolation_method,
            is_interactive=is_interactive,
            show_left=show_left,
            show_right=show_right,
            border_color=border_color,
        )

    def _draw_single_visible_magnifier(
        self,
        *,
        image_to_draw_on: Image.Image,
        display_center_pos: QPoint,
        crop_box_orig: tuple | None,
        magnifier_size: int,
        image_for_crop: Image.Image,
        interpolation_method: str,
        is_interactive: bool,
        border_color: tuple,
    ):
        self.draw_single_magnifier_circle(
            target_image=image_to_draw_on,
            display_center_pos=display_center_pos,
            crop_box_orig=crop_box_orig,
            magnifier_size_pixels=magnifier_size,
            image_for_crop=image_for_crop,
            interpolation_method=interpolation_method,
            is_interactive_render=is_interactive,
            border_color=border_color,
        )

    def _draw_center_diff_magnifier(
        self,
        *,
        image_to_draw_on: Image.Image,
        midpoint: QPoint,
        magnifier_size: int,
        diff_center_patch: Image.Image | None,
        interpolation_method: str,
        border_color: tuple,
    ):
        if not isinstance(diff_center_patch, Image.Image):
            return
        self._draw_single_visible_magnifier(
            image_to_draw_on=image_to_draw_on,
            display_center_pos=midpoint,
            crop_box_orig=None,
            magnifier_size=magnifier_size,
            image_for_crop=diff_center_patch,
            interpolation_method=interpolation_method,
            is_interactive=False,
            border_color=border_color,
        )

    def _compute_diff_combined_position(
        self, *, midpoint: QPoint, magnifier_size: int, layout_horizontal: bool
    ) -> QPoint:
        return compute_diff_combined_position(
            midpoint=midpoint,
            magnifier_size=magnifier_size,
            layout_horizontal=layout_horizontal,
        )

    def _get_magnifier_sizes(self, magnifier_size_pixels: int) -> tuple[int, int]:
        return get_magnifier_sizes(magnifier_size_pixels)

    def _get_combined_magnifier_scaled_content(
        self,
        *,
        crop_box1: tuple,
        crop_box2: tuple,
        content_size: int,
        interpolation_method: str,
        image1_for_crop: Image.Image,
        image2_for_crop: Image.Image,
        is_interactive_render: bool,
        external_cache: dict | None,
    ) -> tuple[Image.Image | None, Image.Image | None]:
        current_cache_key = (
            crop_box1,
            crop_box2,
            content_size,
            interpolation_method,
            image1_for_crop.size,
            image2_for_crop.size,
        )
        if (
            external_cache is not None
            and external_cache.get("key") == current_cache_key
        ):
            return external_cache.get("img1"), external_cache.get("img2")

        scaled1 = self._get_normalized_content(
            image1_for_crop,
            crop_box1,
            content_size,
            interpolation_method,
            is_interactive_render,
        )
        scaled2 = self._get_normalized_content(
            image2_for_crop,
            crop_box2,
            content_size,
            interpolation_method,
            is_interactive_render,
        )
        if external_cache is not None:
            external_cache["key"] = current_cache_key
            external_cache["img1"] = scaled1
            external_cache["img2"] = scaled2
        return scaled1, scaled2

    def _build_combined_magnifier_composite(
        self,
        *,
        scaled1: Image.Image,
        scaled2: Image.Image,
        content_size: int,
        is_horizontal: bool,
        internal_split: float,
        divider_visible: bool,
        divider_color: tuple,
        divider_thickness: int,
    ) -> Image.Image | None:
        composite = scaled1.copy()
        if not is_horizontal:
            split_pos = int(content_size * internal_split)
            if split_pos < content_size:
                composite.paste(
                    scaled2.crop((split_pos, 0, content_size, content_size)),
                    (split_pos, 0),
                )
            self._draw_combined_divider(
                composite=composite,
                split_pos=split_pos,
                content_size=content_size,
                is_horizontal=False,
                divider_visible=divider_visible,
                divider_color=divider_color,
                divider_thickness=divider_thickness,
            )
        else:
            split_pos = int(content_size * internal_split)
            if split_pos < content_size:
                composite.paste(
                    scaled2.crop((0, split_pos, content_size, content_size)),
                    (0, split_pos),
                )
            self._draw_combined_divider(
                composite=composite,
                split_pos=split_pos,
                content_size=content_size,
                is_horizontal=True,
                divider_visible=divider_visible,
                divider_color=divider_color,
                divider_thickness=divider_thickness,
            )
        content_mask = self.get_smooth_circular_mask(content_size)
        if not content_mask:
            return None
        composite.putalpha(content_mask)
        return composite

    def _draw_combined_divider(
        self,
        *,
        composite: Image.Image,
        split_pos: int,
        content_size: int,
        is_horizontal: bool,
        divider_visible: bool,
        divider_color: tuple,
        divider_thickness: int,
    ):
        if not divider_visible or divider_thickness <= 0:
            return
        draw = ImageDraw.Draw(composite)
        if not is_horizontal:
            x0 = split_pos - divider_thickness // 2
            x1 = x0 + divider_thickness - 1
            draw.rectangle([x0, 0, x1, content_size], fill=divider_color)
            return
        y0 = split_pos - divider_thickness // 2
        y1 = y0 + divider_thickness - 1
        draw.rectangle([0, y0, content_size, y1], fill=divider_color)

    def _create_framed_magnifier_widget(
        self,
        *,
        composite: Image.Image,
        magnifier_size_pixels: int,
        border_width: int,
        border_color: tuple,
    ) -> Image.Image | None:
        return create_framed_magnifier_widget(
            composite=composite,
            magnifier_size_pixels=magnifier_size_pixels,
            border_width=border_width,
            border_color=border_color,
        )

    def _paste_magnifier_widget(
        self,
        *,
        target_image: Image.Image,
        display_center_pos: QPoint,
        magnifier_widget: Image.Image | None,
    ):
        paste_magnifier_widget(
            target_image=target_image,
            display_center_pos=display_center_pos,
            magnifier_widget=magnifier_widget,
        )

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

                scaled_content = self._get_normalized_content(
                    image_for_crop,
                    crop_box_orig,
                    content_size,
                    interpolation_method,
                    is_interactive_render,
                )
            else:

                scaled_content = image_for_crop
                if scaled_content.size != (content_size, content_size):
                    scaled_content = scaled_content.resize(
                        (content_size, content_size), Image.Resampling.LANCZOS
                    )

            content_mask = self.get_smooth_circular_mask(content_size)
            if not content_mask:
                return
            scaled_content.putalpha(content_mask)

            border_mask = self.get_smooth_circular_mask(magnifier_size_pixels)
            if not border_mask:
                return

            white_fill = Image.new(
                "RGB", (magnifier_size_pixels, magnifier_size_pixels), border_color[:3]
            )

            final_magnifier_widget = Image.new(
                "RGBA", (magnifier_size_pixels, magnifier_size_pixels), (0, 0, 0, 0)
            )
            final_magnifier_widget.paste(white_fill, (0, 0), border_mask)

            content_paste_pos = border_width - 1
            final_magnifier_widget.alpha_composite(
                scaled_content, (content_paste_pos, content_paste_pos)
            )

            paste_x = display_center_pos.x() - (magnifier_size_pixels // 2)
            paste_y = display_center_pos.y() - (magnifier_size_pixels // 2)
            target_image.alpha_composite(final_magnifier_widget, (paste_x, paste_y))

        except Exception:
            pass
