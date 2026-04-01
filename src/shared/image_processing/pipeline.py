import logging
from dataclasses import dataclass, field
from typing import Optional, Tuple

from PIL import Image
from PyQt6.QtCore import QPoint, QRect

from shared.image_processing.drawing.magnifier_drawer import MagnifierDrawer
from shared.image_processing.drawing.text_drawer import TextDrawer
from shared.image_processing.rendering.base_frame import (
    get_resize_filter,
    resolve_render_images,
)
from shared.image_processing.rendering.geometry import (
    clamp_capture_position as _clamp_capture_position,
    resolve_interpolation as _resolve_interpolation,
)
from shared.image_processing.rendering.magnifier_renderer import (
    render_capture_area_patch,
    render_guides_patch,
    render_magnifier_patch,
)
from shared.image_processing.rendering.overlays import (
    render_divider_patch,
)
from shared.image_processing.rendering.stages import (
    AbortRender,
    DEFAULT_RENDER_STAGES,
    RenderFrameState,
    RenderStage,
    RenderStageDependencies,
)
from shared.image_processing.rendering.text_renderer import (
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
class RenderCanvasContext:
    width: int
    height: int
    split_pos: float
    is_horizontal: bool = False
    divider_line_visible: bool = True
    divider_line_color: Tuple[int, int, int, int] = (255, 255, 255, 255)
    divider_line_thickness: int = 3
    divider_clip_rect: Optional[Tuple[int, int, int, int]] = None

@dataclass
class RenderImageContext:
    image1: Image.Image
    image2: Image.Image
    original_image1: Optional[Image.Image] = None
    original_image2: Optional[Image.Image] = None
    file_name1: str = ""
    file_name2: str = ""
    background_cache_dict: dict | None = None

@dataclass
class RenderModeContext:
    diff_mode: str
    channel_view_mode: str = "RGB"
    interpolation_method: str = "BILINEAR"

@dataclass
class RenderMagnifierContext:
    magnifier_pos: QPoint
    magnifier_offset: Optional[QPoint] = None
    use_magnifier: bool = False
    magnifier_size: float = 0.2
    capture_size: float = 0.1
    show_capture_area: bool = True
    magnifier_drawing_coords: Optional[Tuple] = None
    magnifier_visible_left: bool = True
    magnifier_visible_center: bool = True
    magnifier_visible_right: bool = True
    is_magnifier_combined: bool = False
    magnifier_is_horizontal: bool = False
    magnifier_divider_visible: bool = True
    magnifier_divider_color: Tuple[int, int, int, int] = (255, 255, 255, 230)
    magnifier_divider_thickness: int = 2
    magnifier_internal_split: float = 0.5
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
    magnifier_cache_dict: dict | None = None

@dataclass
class RenderTextContext:
    include_file_names: bool = False
    font_size_percent: int = 100
    font_weight: int = 0
    text_alpha_percent: int = 100
    file_name_color: Tuple[int, int, int, int] = (255, 0, 0, 255)
    file_name_bg_color: Tuple[int, int, int, int] = (0, 0, 0, 80)
    draw_text_background: bool = True
    text_placement_mode: str = "edges"
    max_name_length: int = 50

@dataclass
class RenderContext:
    canvas: RenderCanvasContext
    images: RenderImageContext
    mode: RenderModeContext
    magnifier: RenderMagnifierContext
    text: RenderTextContext = field(default_factory=RenderTextContext)

    @property
    def width(self):
        return self.canvas.width

    @property
    def height(self):
        return self.canvas.height

    @property
    def image1(self):
        return self.images.image1

    @property
    def image2(self):
        return self.images.image2

    @property
    def split_pos(self):
        return self.canvas.split_pos

    @property
    def magnifier_pos(self):
        return self.magnifier.magnifier_pos

    @property
    def diff_mode(self):
        return self.mode.diff_mode

    @property
    def magnifier_offset(self):
        return self.magnifier.magnifier_offset

    @property
    def channel_view_mode(self):
        return self.mode.channel_view_mode

    @property
    def is_horizontal(self):
        return self.canvas.is_horizontal

    @property
    def use_magnifier(self):
        return self.magnifier.use_magnifier

    @property
    def magnifier_size(self):
        return self.magnifier.magnifier_size

    @property
    def capture_size(self):
        return self.magnifier.capture_size

    @property
    def show_capture_area(self):
        return self.magnifier.show_capture_area

    @property
    def divider_line_visible(self):
        return self.canvas.divider_line_visible

    @property
    def divider_line_color(self):
        return self.canvas.divider_line_color

    @property
    def divider_line_thickness(self):
        return self.canvas.divider_line_thickness

    @property
    def divider_clip_rect(self):
        return self.canvas.divider_clip_rect

    @property
    def include_file_names(self):
        return self.text.include_file_names

    @property
    def file_name1(self):
        return self.images.file_name1

    @property
    def file_name2(self):
        return self.images.file_name2

    def __getattr__(self, name):
        for section in (self.canvas, self.images, self.mode, self.magnifier, self.text):
            if hasattr(section, name):
                return getattr(section, name)
        raise AttributeError(name)

class RenderingPipeline:
    DEFAULT_STAGES = DEFAULT_RENDER_STAGES

    def __init__(
        self,
        font_path: Optional[str] = None,
        stages: Optional[tuple[RenderStage, ...] | list[RenderStage]] = None,
    ):
        self.font_path = font_path

        self.text_drawer = _get_global_text_drawer(font_path)
        self.magnifier_drawer = _get_global_magnifier_drawer()
        self.dependencies = RenderStageDependencies(
            font_path=font_path,
            text_drawer=self.text_drawer,
            magnifier_drawer=self.magnifier_drawer,
        )
        self._stages = list(self.DEFAULT_STAGES if stages is None else stages)

    @property
    def stages(self) -> tuple[RenderStage, ...]:
        return tuple(self._stages)

    def append_stage(self, stage: RenderStage) -> None:
        self._stages.append(stage)

    def insert_stage(self, index: int, stage: RenderStage) -> None:
        self._stages.insert(index, stage)

    def replace_stages(self, stages: tuple[RenderStage, ...] | list[RenderStage]) -> None:
        self._stages = list(stages)

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
            frame_state = RenderFrameState(
                ctx=ctx,
                img1_scaled=img1_scaled,
                img2_scaled=img2_scaled,
            )
            for stage in self._stages:
                stage.apply(self.dependencies, frame_state)
            return frame_state.as_render_result()
        except AbortRender as abort:
            return abort.result

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

    def render_magnifier_patch(
        self, ctx: RenderContext
    ) -> tuple[Image.Image | None, QPoint]:
        return render_magnifier_patch(self.dependencies, ctx)

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
        return render_guides_patch(
            self.dependencies, ctx, img_rect, padding_left, padding_top
        )

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
        return render_capture_area_patch(
            self.dependencies, ctx, img_rect, padding_left, padding_top
        )

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
