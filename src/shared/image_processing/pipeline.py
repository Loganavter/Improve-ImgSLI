import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from PIL import Image
from PyQt6.QtCore import QPoint, QRect

from shared.image_processing.drawing.magnifier_drawer import MagnifierDrawer
from shared.image_processing.drawing.text_drawer import TextDrawer
from shared.image_processing.rendering.base_frame import (
    create_final_canvas,
    get_or_create_base_image,
    get_resize_filter,
    resolve_render_images,
)
from shared.image_processing.rendering.geometry import (
    clamp_capture_position as _clamp_capture_position,
    compute_canvas_geometry,
    resolve_interpolation as _resolve_interpolation,
)
from shared.image_processing.rendering.magnifier_renderer import (
    is_effective_magnifier_interactive,
    render_capture_area_patch,
    render_guides_patch,
    render_magnifier_if_needed,
    render_magnifier_patch,
)
from shared.image_processing.rendering.overlays import (
    draw_capture_area_if_needed,
    draw_divider_line_on_canvas,
    render_divider_patch,
)
from shared.image_processing.rendering.text_renderer import (
    draw_file_names_on_canvas,
    render_filenames_patch,
)

logger = logging.getLogger("ImproveImgSLI")

_global_text_drawer = None
_global_text_drawer_font_path = None
_global_magnifier_drawer = None

def _get_global_text_drawer(font_path: Optional[str] = None) -> TextDrawer:
    global _global_text_drawer, _global_text_drawer_font_path

    font_path_str = font_path if font_path else ""

    if _global_text_drawer is None or _global_text_drawer_font_path != font_path_str:
        _global_text_drawer = TextDrawer(font_path_str)
        _global_text_drawer_font_path = font_path_str

    return _global_text_drawer

def _get_global_magnifier_drawer() -> MagnifierDrawer:
    global _global_magnifier_drawer

    if _global_magnifier_drawer is None:
        _global_magnifier_drawer = MagnifierDrawer()

    return _global_magnifier_drawer

@dataclass
class RenderContext:
    width: int
    height: int
    image1: Image.Image
    image2: Image.Image
    split_pos: float
    magnifier_pos: QPoint
    diff_mode: str
    magnifier_offset: Optional[QPoint] = None
    channel_view_mode: str = "RGB"
    is_horizontal: bool = False
    use_magnifier: bool = False
    magnifier_size: float = 0.2
    capture_size: float = 0.1
    show_capture_area: bool = True
    divider_line_visible: bool = True
    divider_line_color: Tuple[int, int, int, int] = (255, 255, 255, 255)
    divider_line_thickness: int = 3
    divider_clip_rect: Optional[Tuple[int, int, int, int]] = None
    include_file_names: bool = False
    file_name1: str = ""
    file_name2: str = ""
    magnifier_is_horizontal: bool = False
    magnifier_divider_visible: bool = True
    magnifier_divider_color: Tuple[int, int, int, int] = (255, 255, 255, 230)
    magnifier_divider_thickness: int = 2
    magnifier_internal_split: float = 0.5
    interpolation_method: str = "BILINEAR"

    original_image1: Optional[Image.Image] = None
    original_image2: Optional[Image.Image] = None

    magnifier_drawing_coords: Optional[Tuple] = None

    magnifier_visible_left: bool = True
    magnifier_visible_center: bool = True
    magnifier_visible_right: bool = True
    is_magnifier_combined: bool = False
    magnifier_border_color: Tuple[int, int, int, int] = (255, 255, 255, 248)
    magnifier_laser_color: Tuple[int, int, int, int] = (255, 255, 255, 255)
    capture_ring_color: Tuple[int, int, int, int] = (255, 50, 100, 230)
    show_magnifier_guides: bool = False
    magnifier_guides_thickness: int = 1
    is_interactive_mode: bool = False
    optimize_magnifier_movement: bool = True
    optimize_laser_smoothing: bool = False
    movement_interpolation_method: str = "BILINEAR"
    magnifier_movement_interpolation_method: str = "BILINEAR"
    laser_smoothing_interpolation_method: str = "BILINEAR"
    magnifier_offset_relative_visual: Optional[QPoint] = None
    magnifier_spacing_relative_visual: float = 0.05
    highlighted_magnifier_element: Optional[str] = None

    font_size_percent: int = 100
    font_weight: int = 0
    text_alpha_percent: int = 100
    file_name_color: Tuple[int, int, int, int] = (255, 0, 0, 255)
    file_name_bg_color: Tuple[int, int, int, int] = (0, 0, 0, 80)
    draw_text_background: bool = True
    text_placement_mode: str = "edges"
    max_name_length: int = 50

    magnifier_cache_dict: dict = None
    background_cache_dict: dict = None

class RenderingPipeline:

    def __init__(self, font_path: Optional[str] = None):
        self.font_path = font_path

        self.text_drawer = _get_global_text_drawer(font_path)
        self.magnifier_drawer = _get_global_magnifier_drawer()

    def _get_highlighted_color(
        self, color: Tuple[int, int, int, int], is_highlighted: bool
    ) -> Tuple[int, int, int, int]:
        if not is_highlighted:
            return color

        return (
            min(255, color[0] + 50),
            min(255, color[1] + 50),
            min(255, color[2] + 50),
            min(255, color[3] + 30),
        )

    def _is_effective_magnifier_interactive(self, ctx: RenderContext) -> bool:
        return is_effective_magnifier_interactive(ctx)

    def render_frame(self, ctx: RenderContext) -> Tuple[
        Optional[Image.Image],
        int,
        int,
        Optional[QRect],
        Optional[QPoint],
        Optional[Image.Image],
    ]:
        img1_scaled, img2_scaled = self._resolve_render_images(ctx)
        if img1_scaled is None or img2_scaled is None:
            return self._make_empty_render_result(ctx)

        try:
            geometry = compute_canvas_geometry(ctx, img1_scaled)
            base_image = get_or_create_base_image(
                ctx, img1_scaled, img2_scaled, self.font_path
            )
            if not base_image:
                return None, 0, 0, None, None, None

            final_canvas = create_final_canvas(base_image, geometry)
            self._draw_divider_if_needed(ctx, final_canvas, geometry)

            combined_center_point = None
            is_separated_layers = getattr(ctx, "return_layers", False)

            self._draw_capture_area_if_needed(ctx, final_canvas, geometry, is_separated_layers)
            magnifier_pil, combined_center_point = self._render_magnifier_if_needed(
                ctx,
                final_canvas,
                img1_scaled,
                img2_scaled,
                geometry,
                is_separated_layers,
            )
            self._draw_file_names_if_needed(ctx, final_canvas, geometry)

            return (
                final_canvas,
                geometry.padding_left,
                geometry.padding_top,
                geometry.magnifier_bbox_on_canvas,
                combined_center_point,
                magnifier_pil,
            )

        except Exception as e:
            logger.error(f"Image generation failed: {e}", exc_info=True)
            return None, 0, 0, None, None, None

    def _make_empty_render_result(self, ctx: RenderContext):
        placeholder = Image.new(
            "RGBA",
            (
                ctx.width if ctx.width > 0 else 1,
                ctx.height if ctx.height > 0 else 1,
            ),
            (0, 0, 0, 0),
        )
        return placeholder, 0, 0, None, None, None

    def _resolve_render_images(self, ctx: RenderContext):
        return resolve_render_images(ctx)

    def _draw_divider_if_needed(
        self, ctx: RenderContext, final_canvas: Image.Image, geometry: dict
    ) -> None:
        if (
            ctx.divider_line_visible
            and ctx.divider_line_thickness > 0
            and ctx.diff_mode == "off"
        ):
            draw_divider_line_on_canvas(
                ctx,
                final_canvas,
                geometry.padding_left,
                geometry.padding_top,
                geometry.img_w,
                geometry.img_h,
            )

    def _draw_capture_area_if_needed(
        self,
        ctx: RenderContext,
        final_canvas: Image.Image,
        geometry: dict,
        is_separated_layers: bool,
    ) -> None:
        draw_capture_area_if_needed(
            self,
            ctx,
            final_canvas,
            geometry,
            is_separated_layers,
        )

    def _render_magnifier_if_needed(
        self,
        ctx: RenderContext,
        final_canvas: Image.Image,
        img1_scaled: Image.Image,
        img2_scaled: Image.Image,
        geometry: dict,
        is_separated_layers: bool,
    ) -> tuple[Image.Image | None, Optional[QPoint]]:
        return render_magnifier_if_needed(
            self,
            ctx,
            final_canvas,
            img1_scaled,
            img2_scaled,
            geometry,
            is_separated_layers,
        )

    def _draw_file_names_if_needed(
        self, ctx: RenderContext, final_canvas: Image.Image, geometry: dict
    ) -> None:
        if ctx.include_file_names:
            draw_file_names_on_canvas(
                self.text_drawer,
                ctx,
                final_canvas,
                geometry.padding_left,
                geometry.padding_top,
                geometry.img_w,
                geometry.img_h,
            )

    def _resize_images(self, ctx: RenderContext) -> Tuple[Image.Image, Image.Image]:
        target_size = (ctx.width, ctx.height)

        if ctx.image1.size == target_size and ctx.image2.size == target_size:
            return ctx.image1, ctx.image2

        img1_resized = ctx.image1.resize(
            target_size, get_resize_filter(ctx.interpolation_method)
        )
        img2_resized = ctx.image2.resize(
            target_size, get_resize_filter(ctx.interpolation_method)
        )

        return img1_resized, img2_resized

    def _get_resize_filter(self, method: str) -> Image.Resampling:
        return get_resize_filter(method)

    def _draw_divider_line_on_canvas(
        self,
        ctx: RenderContext,
        canvas: Image.Image,
        padding_left: int,
        padding_top: int,
        img_w: int,
        img_h: int,
    ):
        draw_divider_line_on_canvas(
            ctx, canvas, padding_left, padding_top, img_w, img_h
        )

    def render_magnifier_patch(
        self, ctx: RenderContext
    ) -> tuple[Image.Image | None, QPoint]:
        return render_magnifier_patch(self, ctx)

    def render_divider_patch(
        self, ctx: RenderContext, img_rect: QRect
    ) -> tuple[Image.Image | None, QPoint]:
        return render_divider_patch(ctx, img_rect)

    def render_guides_patch(
        self, ctx: RenderContext, img_rect: QRect, padding_left: int, padding_top: int
    ) -> tuple[Image.Image | None, QPoint]:
        """
        Рендерит только guides/лазеры от лупы к capture area (Plate Rendering оптимизация).

        Args:
            ctx: Контекст рендеринга
            img_rect: Прямоугольник области изображения
            padding_left: Отступ слева
            padding_top: Отступ сверху

        Returns:
            Tuple[патч с guides, позиция для наложения]
        """
        return render_guides_patch(self, ctx, img_rect, padding_left, padding_top)

    def render_capture_area_patch(
        self, ctx: RenderContext, img_rect: QRect, padding_left: int, padding_top: int
    ) -> tuple[Image.Image | None, QPoint]:
        """
        Рендерит только capture area ring (Plate Rendering оптимизация).

        Args:
            ctx: Контекст рендеринга
            img_rect: Прямоугольник области изображения
            padding_left: Отступ слева
            padding_top: Отступ сверху

        Returns:
            Tuple[патч с capture area, позиция для наложения]
        """
        return render_capture_area_patch(self, ctx, img_rect, padding_left, padding_top)

    def render_filenames_patch(
        self, ctx: RenderContext, img_rect: QRect, padding_left: int, padding_top: int
    ) -> tuple[Image.Image | None, QPoint]:
        """
        Рендерит только имена файлов (Plate Rendering оптимизация).

        Args:
            ctx: Контекст рендеринга
            img_rect: Прямоугольник области изображения
            padding_left: Отступ слева
            padding_top: Отступ сверху

        Returns:
            Tuple[патч с именами файлов, позиция для наложения]
        """
        return render_filenames_patch(self.text_drawer, ctx, img_rect, padding_left, padding_top)

    def _draw_file_names_on_canvas(
        self,
        ctx: RenderContext,
        canvas: Image.Image,
        padding_left: int,
        padding_top: int,
        img_w: int,
        img_h: int,
    ):
        draw_file_names_on_canvas(
            self.text_drawer,
            ctx,
            canvas,
            padding_left,
            padding_top,
            img_w,
            img_h,
        )

def create_render_context_from_store(
    store,
    width: int,
    height: int,
    magnifier_drawing_coords: Optional[Tuple] = None,
    image1_scaled: Optional[Image.Image] = None,
    image2_scaled: Optional[Image.Image] = None,
) -> RenderContext:
    from shared.image_processing.rendering.context_factory import (
        create_render_context_from_store as _impl,
    )

    return _impl(
        store=store,
        width=width,
        height=height,
        magnifier_drawing_coords=magnifier_drawing_coords,
        image1_scaled=image1_scaled,
        image2_scaled=image2_scaled,
    )

def create_render_context_from_params(
    render_params_dict: dict,
    width: int,
    height: int,
    magnifier_drawing_coords: Optional[Tuple] = None,
    image1_scaled: Optional[Image.Image] = None,
    image2_scaled: Optional[Image.Image] = None,
    original_image1: Optional[Image.Image] = None,
    original_image2: Optional[Image.Image] = None,
    file_name1: str = "",
    file_name2: str = "",
    session_caches: dict = None,
) -> RenderContext:
    from shared.image_processing.rendering.context_factory import (
        create_render_context_from_params as _impl,
    )

    return _impl(
        render_params_dict=render_params_dict,
        width=width,
        height=height,
        magnifier_drawing_coords=magnifier_drawing_coords,
        image1_scaled=image1_scaled,
        image2_scaled=image2_scaled,
        original_image1=original_image1,
        original_image2=original_image2,
        file_name1=file_name1,
        file_name2=file_name2,
        session_caches=session_caches,
    )
