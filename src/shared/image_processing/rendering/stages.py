from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Protocol

from PIL import Image
from PyQt6.QtCore import QPoint, QRect

from shared.image_processing.rendering.base_frame import (
    create_final_canvas,
    get_or_create_base_image,
)
from shared.image_processing.rendering.geometry import compute_canvas_geometry
from shared.image_processing.rendering.magnifier_renderer import (
    render_magnifier_if_needed,
)
from shared.image_processing.rendering.overlays import (
    draw_capture_area_if_needed,
    draw_divider_line_on_canvas,
)
from shared.image_processing.rendering.text_renderer import draw_file_names_on_canvas

if TYPE_CHECKING:
    from shared.image_processing.drawing.magnifier_drawer import MagnifierDrawer
    from shared.image_processing.drawing.text_drawer import TextDrawer
    from shared.image_processing.pipeline import RenderContext

@dataclass(frozen=True)
class RenderStageDependencies:
    font_path: Optional[str]
    text_drawer: "TextDrawer"
    magnifier_drawer: "MagnifierDrawer"

    def _get_highlighted_color(
        self, color: tuple[int, int, int, int], is_highlighted: bool
    ) -> tuple[int, int, int, int]:
        return self.get_highlighted_color(color, is_highlighted)

    def get_highlighted_color(
        self, color: tuple[int, int, int, int], is_highlighted: bool
    ) -> tuple[int, int, int, int]:
        if not is_highlighted:
            return color
        return (
            min(255, color[0] + 50),
            min(255, color[1] + 50),
            min(255, color[2] + 50),
            min(255, color[3] + 30),
        )

@dataclass
class RenderFrameState:
    ctx: "RenderContext"
    img1_scaled: Image.Image
    img2_scaled: Image.Image
    geometry: object | None = None
    base_image: Image.Image | None = None
    final_canvas: Image.Image | None = None
    is_separated_layers: bool = False
    combined_center_point: QPoint | None = None
    magnifier_pil: Image.Image | None = None

    def as_render_result(
        self,
    ) -> tuple[
        Optional[Image.Image],
        int,
        int,
        Optional[QRect],
        Optional[QPoint],
        Optional[Image.Image],
    ]:
        if self.final_canvas is None or self.geometry is None:
            return None, 0, 0, None, None, None
        return (
            self.final_canvas,
            self.geometry.padding_left,
            self.geometry.padding_top,
            self.geometry.magnifier_bbox_on_canvas,
            self.combined_center_point,
            self.magnifier_pil,
        )

class RenderStage(Protocol):
    name: str

    def apply(
        self,
        dependencies: RenderStageDependencies,
        frame_state: RenderFrameState,
    ) -> None:
        ...

class AbortRender(Exception):
    def __init__(self, result):
        super().__init__("render aborted")
        self.result = result

class PrepareCanvasStage:
    name = "prepare_canvas"

    def apply(
        self,
        dependencies: RenderStageDependencies,
        frame_state: RenderFrameState,
    ) -> None:
        frame_state.geometry = compute_canvas_geometry(
            frame_state.ctx,
            frame_state.img1_scaled,
        )
        frame_state.base_image = get_or_create_base_image(
            frame_state.ctx,
            frame_state.img1_scaled,
            frame_state.img2_scaled,
            dependencies.font_path,
        )
        if not frame_state.base_image:
            raise AbortRender((None, 0, 0, None, None, None))
        frame_state.final_canvas = create_final_canvas(
            frame_state.base_image,
            frame_state.geometry,
        )
        frame_state.is_separated_layers = bool(
            getattr(frame_state.ctx, "return_layers", False)
        )

class DividerStage:
    name = "divider"

    def apply(
        self,
        dependencies: RenderStageDependencies,
        frame_state: RenderFrameState,
    ) -> None:
        ctx = frame_state.ctx
        if (
            ctx.canvas.divider_line_visible
            and ctx.canvas.divider_line_thickness > 0
            and ctx.mode.diff_mode == "off"
        ):
            draw_divider_line_on_canvas(
                ctx,
                frame_state.final_canvas,
                frame_state.geometry.padding_left,
                frame_state.geometry.padding_top,
                frame_state.geometry.img_w,
                frame_state.geometry.img_h,
            )

class CaptureAreaStage:
    name = "capture_area"

    def apply(
        self,
        dependencies: RenderStageDependencies,
        frame_state: RenderFrameState,
    ) -> None:
        draw_capture_area_if_needed(
            dependencies,
            frame_state.ctx,
            frame_state.final_canvas,
            frame_state.geometry,
            frame_state.is_separated_layers,
        )

class MagnifierStage:
    name = "magnifier"

    def apply(
        self,
        dependencies: RenderStageDependencies,
        frame_state: RenderFrameState,
    ) -> None:
        (
            frame_state.magnifier_pil,
            frame_state.combined_center_point,
        ) = render_magnifier_if_needed(
            dependencies,
            frame_state.ctx,
            frame_state.final_canvas,
            frame_state.img1_scaled,
            frame_state.img2_scaled,
            frame_state.geometry,
            frame_state.is_separated_layers,
        )

class FileNamesStage:
    name = "file_names"

    def apply(
        self,
        dependencies: RenderStageDependencies,
        frame_state: RenderFrameState,
    ) -> None:
        if frame_state.ctx.text.include_file_names:
            draw_file_names_on_canvas(
                dependencies.text_drawer,
                frame_state.ctx,
                frame_state.final_canvas,
                frame_state.geometry.padding_left,
                frame_state.geometry.padding_top,
                frame_state.geometry.img_w,
                frame_state.geometry.img_h,
            )

DEFAULT_RENDER_STAGES: tuple[RenderStage, ...] = (
    PrepareCanvasStage(),
    DividerStage(),
    CaptureAreaStage(),
    MagnifierStage(),
    FileNamesStage(),
)
