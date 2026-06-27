from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class BaseCanvasProtocol(Protocol):
    firstFrameRendered: object
    firstVisualFrameReady: object
    zoomChanged: object
    mousePressed: object
    mouseMoved: object
    mouseReleased: object
    wheelScrolled: object
    keyPressed: object
    keyReleased: object

    zoom_level: float
    pan_offset_x: float
    pan_offset_y: float
    split_position: float
    is_horizontal: bool

    def set_store(self, store) -> None: ...
    def set_render_scene(self, scene) -> None: ...
    def set_split_position_sync(self, sync_callback) -> None: ...
    def set_split_pos(self, pos: float) -> None: ...
    def set_apply_channel_mode_in_shader(self, enabled: bool) -> None: ...

    def set_layers(
        self, background=None, overlay=None, overlay_pos=None, coords_snapshot=None
    ) -> None: ...
    def set_feature_overlay_content(self, pixmap, top_left) -> None: ...
    def set_overlay_coords(
        self,
        capture_center,
        capture_radius: float,
        overlay_centers: list,
        overlay_radius: float,
    ) -> None: ...
    def set_guides_params(self, visible: bool, color, thickness: int) -> None: ...
    def set_capture_color(self, color) -> None: ...
    def set_capture_area(self, center, size: int | float, color=None) -> None: ...
    def upload_diff_source_pil_image(self, pil_image) -> None: ...
    def clear_feature_overlay_gpu(self): ...
    def set_feature_overlay_gpu_params(
        self,
        slots: list[dict | None],
        channel_mode: int = 0,
        diff_mode: int = 0,
        diff_threshold: float = 20.0 / 255.0,
        border_color=None,
        border_width: float = 2.0,
        interp_mode: int = 1,
    ) -> None: ...
    def begin_update_batch(self) -> None: ...
    def end_update_batch(self) -> None: ...
    def clear(self) -> None: ...
    def setPixmap(self, pixmap) -> None: ...


@runtime_checkable
class GlLikeCanvasProtocol(BaseCanvasProtocol, Protocol):
    def set_pil_layers(
        self,
        pil_image1=None,
        pil_image2=None,
        overlay=None,
        overlay_pos=None,
        source_image1=None,
        source_image2=None,
        source_key=None,
        shader_letterbox: bool = False,
    ) -> None: ...


@runtime_checkable
class ExportCanvasProtocol(BaseCanvasProtocol, Protocol):
    def configure_offscreen_render(
        self,
        *,
        stored_images,
        source_images,
        content_rect: tuple[int, int, int, int],
        shader_letterbox: bool = False,
    ) -> None: ...

    def grabFramebuffer(self): ...
