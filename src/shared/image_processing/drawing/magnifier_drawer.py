from PIL import Image
from PyQt6.QtCore import QPoint

from core.store import Store
from shared.image_processing.drawing.magnifier_compositor import MagnifierCompositor
from shared.image_processing.drawing.magnifier_crop_service import (
    MagnifierCropService,
)
from shared.image_processing.drawing.magnifier_diff_service import MagnifierDiffService
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
from shared.image_processing.drawing.magnifier_masks import get_smooth_circular_mask
from shared.image_processing.drawing.magnifier_strategies import (
    draw_diff_combined_bottom_magnifier,
    draw_strategy_combined_single,
    draw_strategy_diff_top_combined_bottom,
    draw_strategy_three_magnifiers,
    draw_strategy_two_magnifiers,
    draw_visible_side_magnifiers,
)

class MagnifierDrawer:
    def __init__(self):
        self._mask_image_cache = None
        self._mask_path_checked = False
        self._resized_mask_cache = {}
        self.crop_service = MagnifierCropService()
        self.diff_service = MagnifierDiffService()
        self.compositor = MagnifierCompositor()

    def _create_diff_image(
        self,
        image1: Image.Image,
        image2: Image.Image | None,
        mode: str = "highlight",
        threshold: int = 20,
        font_path: str | None = None,
    ) -> Image.Image | None:
        return self.diff_service.create_diff_image(
            image1=image1,
            image2=image2,
            mode=mode,
            threshold=threshold,
            font_path=font_path,
        )

    def get_smooth_circular_mask(self, size: int) -> Image.Image | None:
        return get_smooth_circular_mask(size)

    def _should_use_subpixel(self, crop_box1: tuple, crop_box2: tuple) -> bool:
        return self.crop_service.should_use_subpixel(crop_box1, crop_box2)

    def _compute_crop_boxes_subpixel(
        self, image1: Image.Image, image2: Image.Image, store: Store
    ) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float]]:
        return self.crop_service.compute_crop_boxes_subpixel(image1, image2, store)

    def _compute_single_crop_box_subpixel(
        self,
        width: int,
        height: int,
        rel_x: float,
        rel_y: float,
        capture_size_relative: float,
    ) -> tuple[float, float, float, float]:
        return self.crop_service.compute_single_crop_box_subpixel(
            width=width,
            height=height,
            rel_x=rel_x,
            rel_y=rel_y,
            capture_size_relative=capture_size_relative,
        )

    def _get_normalized_content(
        self,
        img: Image.Image,
        box: tuple,
        target_size: int,
        interpolation_method: str,
        is_interactive: bool,
    ) -> Image.Image:
        return self.crop_service.get_normalized_content(
            img=img,
            box=box,
            target_size=target_size,
            interpolation_method=interpolation_method,
            is_interactive=is_interactive,
        )

    def draw_capture_area(
        self,
        image_to_draw_on: Image.Image,
        center_pos: QPoint,
        size: int,
        thickness: int | None = None,
        color: tuple = (255, 50, 100, 230),
    ):
        self.compositor.draw_capture_area(
            image_to_draw_on=image_to_draw_on,
            center_pos=center_pos,
            size=size,
            thickness=thickness,
            color=color,
        )

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
        show_left = getattr(store.viewport.view_state, "magnifier_visible_left", True)
        show_center = getattr(store.viewport.view_state, "magnifier_visible_center", True)
        show_right = getattr(store.viewport.view_state, "magnifier_visible_right", True)
        diff_mode = getattr(store.viewport.view_state, "diff_mode", "off")
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
                comb_is_horizontal=kwargs["store"].viewport.view_state.magnifier_is_horizontal,
                comb_split=kwargs["internal_split"],
                comb_divider_visible=kwargs["divider_visible"],
                comb_divider_color=kwargs["divider_color"],
                comb_divider_thickness=kwargs["divider_thickness"],
                layout_horizontal=kwargs["store"].viewport.view_state.is_horizontal,
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
            is_horizontal=kwargs["store"].viewport.view_state.magnifier_is_horizontal,
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
        kwargs["midpoint"] = kwargs.get("magnifier_midpoint_target")
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
                layout_horizontal=context["store"].viewport.view_state.is_horizontal,
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
            layout_horizontal=context["store"].viewport.view_state.magnifier_is_horizontal,
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
        self.compositor.draw_combined_magnifier_circle(
            crop_service=self.crop_service,
            target_image=target_image,
            display_center_pos=display_center_pos,
            crop_box1=crop_box1,
            crop_box2=crop_box2,
            magnifier_size_pixels=magnifier_size_pixels,
            image1_for_crop=image1_for_crop,
            image2_for_crop=image2_for_crop,
            interpolation_method=interpolation_method,
            is_horizontal=is_horizontal,
            is_interactive_render=is_interactive_render,
            internal_split=internal_split,
            divider_visible=divider_visible,
            divider_color=divider_color,
            divider_thickness=divider_thickness,
            border_color=border_color,
            external_cache=external_cache,
        )

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
        return self.compositor.get_combined_magnifier_scaled_content(
            crop_service=self.crop_service,
            crop_box1=crop_box1,
            crop_box2=crop_box2,
            content_size=content_size,
            interpolation_method=interpolation_method,
            image1_for_crop=image1_for_crop,
            image2_for_crop=image2_for_crop,
            is_interactive_render=is_interactive_render,
            external_cache=external_cache,
        )

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
        return self.compositor.build_combined_magnifier_composite(
            scaled1=scaled1,
            scaled2=scaled2,
            content_size=content_size,
            is_horizontal=is_horizontal,
            internal_split=internal_split,
            divider_visible=divider_visible,
            divider_color=divider_color,
            divider_thickness=divider_thickness,
        )

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
        self.compositor.draw_combined_divider(
            composite=composite,
            split_pos=split_pos,
            content_size=content_size,
            is_horizontal=is_horizontal,
            divider_visible=divider_visible,
            divider_color=divider_color,
            divider_thickness=divider_thickness,
        )

    def _create_framed_magnifier_widget(
        self,
        *,
        composite: Image.Image,
        magnifier_size_pixels: int,
        border_width: int,
        border_color: tuple,
    ) -> Image.Image | None:
        return self.compositor.create_framed_magnifier_widget(
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
        self.compositor.paste_magnifier_widget(
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
        self.compositor.draw_single_magnifier_circle(
            crop_service=self.crop_service,
            target_image=target_image,
            display_center_pos=display_center_pos,
            crop_box_orig=crop_box_orig,
            magnifier_size_pixels=magnifier_size_pixels,
            image_for_crop=image_for_crop,
            interpolation_method=interpolation_method,
            is_interactive_render=is_interactive_render,
            border_color=border_color,
        )
