from PIL import Image as PilImage
from PySide6.QtCore import QPoint, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QRhiWidget

from .interaction import (
    handle_key_press_event,
    handle_key_release_event,
    handle_leave_event,
    handle_mouse_move_event,
    handle_mouse_press_event,
    handle_mouse_release_event,
    handle_wheel_event,
    paste_overlay_button_at,
    reset_view as reset_view_impl,
    set_drag_overlay_state as set_drag_overlay_state_impl,
    set_capture_area as set_capture_area_impl,
    set_capture_color as set_capture_color_impl,
    set_guides_params as set_guides_params_impl,
    set_overlay_coords as set_overlay_coords_impl,
    set_pan as set_pan_impl,
    set_paste_overlay_hover,
    set_paste_overlay_state as set_paste_overlay_state_impl,
    set_zoom as set_zoom_impl,
    update_paste_overlay_rects,
    update_split_for_zoom,
)
from .rhi_render import render_clear_frame
from .rhi_renderer import RhiCanvasRenderer
from .rhi_backend import configure_rhi_widget, log_initialized_rhi_widget
from .render_context import (
    begin_update_batch,
    emit_viewport_state_change,
    end_update_batch,
    preload_source_textures,
    request_update,
    resize_gl,
    schedule_source_preload,
)
from .scene import build_gl_render_scene
from .state import init_widget_state
from .texture_parts.base_images import (
    configure_offscreen_render,
    get_letterbox_params,
    letterbox_pil,
    update_letterbox_geometry,
    upload_diff_source_pil_image,
    upload_image,
    upload_pil_images,
    upload_source_pil_image,
)
from .texture_parts.common import set_texture_filter
from .texture_parts.layers import (
    clear as clear_textures_and_layers,
    set_background,
    set_layers,
    set_pil_layers,
    set_pixmap,
)
from .feature_overlay_gpu import (
    clear_feature_overlay_gpu,
    set_feature_overlay_content,
    set_feature_overlay_gpu_params,
    upload_feature_overlay_crop,
    upload_feature_overlay_pair,
)

class GLCanvas(QRhiWidget):
    mousePressed = Signal(object)
    mouseMoved = Signal(object)
    mouseReleased = Signal(object)
    wheelScrolled = Signal(object)
    zoomChanged = Signal(float)
    keyPressed = Signal(object)
    keyReleased = Signal(object)
    pasteOverlayDirectionSelected = Signal(str)
    pasteOverlayCancelled = Signal()
    firstFrameRendered = Signal()
    firstVisualFrameReady = Signal()

    _alignment = Qt.AlignmentFlag.AlignCenter

    def __init__(self, parent=None):
        super().__init__(parent)
        configure_rhi_widget(self)
        self._first_frame_rendered_emitted = False
        self._rhi_renderer = RhiCanvasRenderer()
        init_widget_state(self)

    def set_store(self, store):
        state = self.runtime_state
        state._store = store
        state._render_scene = build_gl_render_scene(
            store, apply_channel_mode_in_shader=state._apply_channel_mode_in_shader
        )
        if hasattr(store, "on_change"):
            store.on_change(lambda scope: self._refresh_render_scene())

    def _refresh_render_scene(self):
        state = self.runtime_state
        if not getattr(state, "_render_scene_dirty", False):
            state._render_scene_dirty = True
            QTimer.singleShot(0, self._flush_render_scene)
        self.update()

    def _flush_render_scene(self):
        state = self.runtime_state
        if not getattr(state, "_render_scene_dirty", False):
            return
        state._render_scene_dirty = False
        if state._store is None:
            return
        state._render_scene = build_gl_render_scene(
            state._store, apply_channel_mode_in_shader=state._apply_channel_mode_in_shader
        )
        plan = getattr(self, "_active_render_plan", None)
        if plan is not None:
            from ui.canvas_infra.scene.widget_registry import (
                apply_canvas_feature_live_runtime_overlays,
            )
            apply_canvas_feature_live_runtime_overlays(state._store, self)
        self.update()

    def set_apply_channel_mode_in_shader(self, enabled: bool):
        state = self.runtime_state
        state._apply_channel_mode_in_shader = enabled
        if state._store is not None:
            state._render_scene = build_gl_render_scene(
                state._store, apply_channel_mode_in_shader=state._apply_channel_mode_in_shader
            )
        self.update()

    def set_render_scene(self, scene):
        self.runtime_state._render_scene = scene
        self.update()

    def set_split_position_sync(self, sync_callback):
        self.runtime_state._split_position_sync = sync_callback

    def set_drag_overlay_state(
        self,
        visible: bool,
        horizontal: bool = False,
        text1: str = "",
        text2: str = "",
    ):
        set_drag_overlay_state_impl(self, visible, horizontal, text1, text2)

    def is_drag_overlay_visible(self) -> bool:
        return bool(self.runtime_state._drag_overlay_visible)

    def resizeEvent(self, event):
        state = self.runtime_state
        state._drag_overlay_cache_key = None
        state._drag_overlay_cached_image = None
        super().resizeEvent(event)
        size = event.size()
        resize_gl(self, size.width(), size.height())

    def _update_paste_overlay_rects(self):
        update_paste_overlay_rects(self)

    def set_paste_overlay_state(
        self,
        visible: bool,
        is_horizontal: bool = False,
        texts: dict | None = None,
    ):
        set_paste_overlay_state_impl(self, visible, is_horizontal, texts)

    def is_paste_overlay_visible(self) -> bool:
        return bool(self.runtime_state._paste_overlay_visible)

    def _paste_overlay_button_at(self, pos: QPointF | QPoint) -> str | None:
        return paste_overlay_button_at(self, pos)

    def _set_paste_overlay_hover(self, hovered: str | None):
        set_paste_overlay_hover(self, hovered)

    def initialize(self, command_buffer):
        log_initialized_rhi_widget(self)
        self._rhi_renderer.initialize(self, command_buffer)

    def releaseResources(self):
        self._rhi_renderer.release()

    def upload_image(self, qimage: QImage, slot_index: int):
        return upload_image(self, qimage, slot_index)

    def upload_image2(self, qimage: QImage):
        self.upload_image(qimage, 1)

    def _letterbox_pil(self, img: PilImage.Image, slot_index: int = -1) -> PilImage.Image:
        return letterbox_pil(self, img, slot_index)

    def upload_pil_images(
        self,
        pil_image1,
        pil_image2,
        source_image1=None,
        source_image2=None,
        source_key=None,
        display_cache_key=None,
        shader_letterbox: bool = False,
    ):
        return upload_pil_images(
            self,
            pil_image1,
            pil_image2,
            source_image1,
            source_image2,
            source_key,
            display_cache_key,
            shader_letterbox,
        )

    def render(self, command_buffer):
        render_clear_frame(self, command_buffer)
        if not self._first_frame_rendered_emitted:
            self._first_frame_rendered_emitted = True
            self.firstFrameRendered.emit()
            self.firstVisualFrameReady.emit()

    def _request_update(self):
        request_update(self)

    def _emit_viewport_state_change(self):
        emit_viewport_state_change(self)

    def _schedule_source_preload(self):
        schedule_source_preload(self)

    def _preload_source_textures(self):
        preload_source_textures(self)

    def begin_update_batch(self):
        begin_update_batch(self)

    def end_update_batch(self):
        end_update_batch(self)

    def set_split_pos(self, pos: float):
        self.split_position = pos
        self._request_update()

    def set_background(self, pixmap: QPixmap | None):
        return set_background(self, pixmap)

    def set_pixmap(self, pixmap: QPixmap | None):
        return set_pixmap(self, pixmap)

    def set_feature_overlay_content(self, pixmap: QPixmap | None, top_left: QPoint | None):
        return set_feature_overlay_content(self, pixmap, top_left)

    def get_letterbox_params(self, slot: int = 0) -> tuple:
        return get_letterbox_params(self, slot)

    def set_feature_overlay_gpu_params(
        self,
        slots: list[dict | None],
        channel_mode: int = 0,
        diff_mode: int = 0,
        diff_threshold: float = 20.0 / 255.0,
        border_color: QColor | None = None,
        border_width: float = 2.0,
        interp_mode: int = 1,
    ):
        return set_feature_overlay_gpu_params(
            self, slots, channel_mode, diff_mode, diff_threshold, border_color, border_width, interp_mode
        )

    def _set_texture_filter(self, texture_id: int, gl_filter: int):
        return set_texture_filter(self, texture_id, gl_filter)

    def clear_feature_overlay_gpu(self):
        return clear_feature_overlay_gpu(self)

    def upload_feature_overlay_crop(self, pil_image, center: QPointF, radius: float,
                                    border_color: QColor | None = None, border_width: float = 2.0,
                                    index: int = 0, gl_filter: int = None):
        return upload_feature_overlay_crop(
            self, pil_image, center, radius, border_color, border_width, index, gl_filter
        )

    def upload_feature_overlay_pair(self, pil1, pil2, center: QPointF, radius: float,
                                    split: float = 0.5, horizontal: bool = False,
                                    divider_visible: bool = True, divider_color: tuple = (1.0, 1.0, 1.0, 0.9),
                                    divider_thickness: int = 2,
                                    border_color: QColor | None = None, border_width: float = 2.0,
                                    index: int = 0, gl_filter: int = None):
        return upload_feature_overlay_pair(
            self,
            pil1,
            pil2,
            center,
            radius,
            split,
            horizontal,
            divider_visible,
            divider_color,
            divider_thickness,
            border_color,
            border_width,
            index,
            gl_filter,
        )

    def upload_diff_source_pil_image(self, pil_image):
        return upload_diff_source_pil_image(self, pil_image)

    def configure_offscreen_render(
        self,
        *,
        stored_images,
        source_images,
        content_rect: tuple[int, int, int, int],
        shader_letterbox: bool = False,
    ):
        return configure_offscreen_render(
            self,
            stored_images=stored_images,
            source_images=source_images,
            content_rect=content_rect,
            shader_letterbox=shader_letterbox,
        )

    def set_overlay_coords(
        self,
        capture_center: QPointF | None,
        capture_radius: float,
        overlay_centers: list[QPointF],
        overlay_radius: float,
    ):
        set_overlay_coords_impl(self, capture_center, capture_radius, overlay_centers, overlay_radius)

    def set_guides_params(self, visible: bool, color: QColor, thickness: int):
        set_guides_params_impl(self, visible, color, thickness)

    def set_capture_color(self, color: QColor):
        set_capture_color_impl(self, color)

    def set_capture_area(
        self, center: QPoint | None, size: int, color: QColor | None = None
    ):
        set_capture_area_impl(self, center, size, color)

    def set_layers(
        self,
        background: QPixmap | None,
        overlay: QPixmap | None,
        overlay_pos: QPoint | None,
        coords_snapshot: tuple | None = None,
    ):
        return set_layers(self, background, overlay, overlay_pos, coords_snapshot)

    def set_pil_layers(
        self,
        pil_image1=None,
        pil_image2=None,
        overlay=None,
        overlay_pos=None,
        source_image1=None,
        source_image2=None,
        source_key=None,
        display_cache_key=None,
        shader_letterbox: bool = False,
    ):
        return set_pil_layers(
            self,
            pil_image1,
            pil_image2,
            overlay,
            overlay_pos,
            source_image1,
            source_image2,
            source_key,
            display_cache_key,
            shader_letterbox,
        )

    def setPixmap(self, pixmap: QPixmap | None):
        return set_pixmap(self, pixmap)

    def clear(self):
        return clear_textures_and_layers(self)

    def setAlignment(self, alignment):
        self._alignment = alignment

    def alignment(self):
        return self._alignment

    def set_read_only(self, enabled: bool):
        self.runtime_state._read_only = bool(enabled)
        if enabled:
            from ui.canvas_infra.viewport.state import set_pan_offsets, set_zoom_level

            set_zoom_level(self, 1.0)
            set_pan_offsets(self, 0.0, 0.0)
            self.update()

    def is_read_only(self) -> bool:
        return bool(getattr(self.runtime_state, "_read_only", False))

    def setAutoFillBackground(self, enabled):

        pass

    def setFocusPolicy(self, policy):
        super().setFocusPolicy(policy)

    def setAttribute(self, attribute, on=True):
        super().setAttribute(attribute, on)

    def contentsRect(self):
        return self.rect()

    def _update_split_for_zoom(self, new_zoom, new_pan_x, new_pan_y):
        update_split_for_zoom(self, new_zoom, new_pan_x, new_pan_y)

    def set_zoom(self, zoom: float):
        set_zoom_impl(self, zoom)

    def set_pan(self, x: float, y: float):
        set_pan_impl(self, x, y)

    def reset_view(self):
        reset_view_impl(self)

    def wheelEvent(self, event):
        handle_wheel_event(self, event)

    def mousePressEvent(self, event):
        handle_mouse_press_event(self, event)

    def mouseReleaseEvent(self, event):
        handle_mouse_release_event(self, event)

    def mouseMoveEvent(self, event):
        handle_mouse_move_event(self, event)

    def keyPressEvent(self, event):
        handle_key_press_event(self, event)

    def keyReleaseEvent(self, event):
        handle_key_release_event(self, event)

    def leaveEvent(self, event):
        handle_leave_event(self, event)
