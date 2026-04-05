from __future__ import annotations

import logging

from PIL import Image as PilImage
from PyQt6.QtCore import QPoint, QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPalette, QPixmap
from PyQt6.QtOpenGL import QOpenGLWindow
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from .interaction import (
    handle_key_press_event,
    handle_key_release_event,
    handle_mouse_move_event,
    handle_mouse_press_event,
    handle_mouse_release_event,
    handle_wheel_event,
    paste_overlay_button_at,
    reset_view as reset_view_impl,
    set_capture_area as set_capture_area_impl,
    set_capture_color as set_capture_color_impl,
    set_drag_overlay_state as set_drag_overlay_state_impl,
    set_guides_params as set_guides_params_impl,
    set_overlay_coords as set_overlay_coords_impl,
    set_pan as set_pan_impl,
    set_paste_overlay_hover,
    set_paste_overlay_state as set_paste_overlay_state_impl,
    set_split_line_params as set_split_line_params_impl,
    set_zoom as set_zoom_impl,
    update_paste_overlay_rects,
    update_split_for_zoom,
)
from .render import paint_gl
from .render_context import (
    begin_update_batch,
    emit_viewport_state_change,
    end_update_batch,
    initialize_gl_resources,
    preload_source_textures,
    request_update,
    resize_gl,
    schedule_source_preload,
)
from .scene import build_gl_render_scene
from .state import init_widget_state
from .textures import (
    clear as clear_textures_and_layers,
    clear_magnifier_gpu,
    configure_offscreen_render,
    get_letterbox_params,
    letterbox_pil,
    set_background,
    set_layers,
    set_magnifier_content,
    set_magnifier_gpu_params,
    set_pil_layers,
    set_pixmap,
    set_texture_filter,
    upload_combined_magnifier,
    upload_diff_source_pil_image,
    upload_image,
    upload_magnifier_crop,
    upload_pil_images,
    upload_source_pil_image,
    update_letterbox_geometry,
)

logger = logging.getLogger("ImproveImgSLI")

class _CanvasWindow(QOpenGLWindow):
    def __init__(self, host):
        super().__init__()
        self._host = host
        self.setFlags(Qt.WindowType.FramelessWindowHint)
        if hasattr(self, "setColor"):
            self.setColor(QColor(0, 0, 0, 0))
        self.frameSwapped.connect(self._on_frame_swapped)

    def _on_frame_swapped(self):
        self._host._emit_first_frame_rendered()

    def initializeGL(self):
        initialize_gl_resources(self._host)

    def paintGL(self):
        return paint_gl(self._host)

    def resizeGL(self, w, h):
        resize_gl(self._host, w, h)

    def mousePressEvent(self, event):
        handle_mouse_press_event(self._host, event)

    def mouseReleaseEvent(self, event):
        handle_mouse_release_event(self._host, event)

    def mouseMoveEvent(self, event):
        handle_mouse_move_event(self._host, event)

    def wheelEvent(self, event):
        handle_wheel_event(self._host, event)

    def keyPressEvent(self, event):
        handle_key_press_event(self._host, event)

    def keyReleaseEvent(self, event):
        handle_key_release_event(self._host, event)

    def leaveEvent(self, event):
        if self._host.runtime_state._paste_overlay_visible:
            set_paste_overlay_hover(self._host, None)
        super().leaveEvent(event)

class GLCanvas(QWidget):
    supports_legacy_gl_magnifier = True
    uses_quick_canvas_overlay = False

    mousePressed = pyqtSignal(object)
    mouseMoved = pyqtSignal(object)
    mouseReleased = pyqtSignal(object)
    wheelScrolled = pyqtSignal(object)
    zoomChanged = pyqtSignal(float)
    keyPressed = pyqtSignal(object)
    keyReleased = pyqtSignal(object)
    pasteOverlayDirectionSelected = pyqtSignal(str)
    pasteOverlayCancelled = pyqtSignal()
    firstFrameRendered = pyqtSignal()
    firstVisualFrameReady = pyqtSignal()

    _alignment = Qt.AlignmentFlag.AlignCenter
    _PROXY_ATTRS = {
        "_store",
        "_render_scene",
        "_split_position_sync",
        "_clip_overlays_to_content_rect",
        "_preview_source_key",
        "_preview_fit_content",
        "_apply_channel_mode_in_shader",
        "_source_images_ready",
        "_source_pil_images",
        "_stored_pil_images",
        "_source_texture_ids",
        "_diff_source_texture_id",
        "_mag_tex_ids",
        "_mag_combined_tex_ids",
        "_circle_mask_tex_id",
        "_mag_tex_id",
        "_circle_shader",
        "_guides_tex_id",
        "_ui_overlay_tex_id",
        "_quad_vertices",
        "shader_program",
        "vao",
        "vbo",
        "textures",
        "texture_ids",
        "zoom_level",
        "pan_offset_x",
        "pan_offset_y",
        "split_position",
        "is_horizontal",
        "runtime_state",
        "_pan_dragging",
        "_pan_last_pos",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        object.__setattr__(self, "_first_frame_rendered_emitted", False)
        object.__setattr__(self, "_canvas_window", _CanvasWindow(self))
        object.__setattr__(
            self,
            "_window_container",
            QWidget.createWindowContainer(self._canvas_window, self),
        )
        self.setAcceptDrops(True)
        self._window_container.setAcceptDrops(True)
        self._window_container.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)
        self._window_container.setAutoFillBackground(True)
        self._window_container.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._window_container.setMouseTracking(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._window_container)
        init_widget_state(self)
        self.setFocusProxy(self._window_container)
        self._sync_native_background()

    def _emit_first_frame_rendered(self):
        if self._first_frame_rendered_emitted:
            return
        self._first_frame_rendered_emitted = True
        self.firstFrameRendered.emit()
        self.firstVisualFrameReady.emit()

    def __getattr__(self, name):
        if name in self._PROXY_ATTRS:
            window = object.__getattribute__(self, "_canvas_window")
            return getattr(window, name)
        raise AttributeError(name)

    def __setattr__(self, name, value):
        if name in {"_canvas_window", "_window_container", "_first_frame_rendered_emitted"}:
            object.__setattr__(self, name, value)
            return
        if name in type(self)._PROXY_ATTRS and "_canvas_window" in self.__dict__:
            setattr(self._canvas_window, name, value)
            return
        super().__setattr__(name, value)

    def installEventFilter(self, obj):
        super().installEventFilter(obj)
        self._window_container.installEventFilter(obj)
        self._canvas_window.installEventFilter(obj)

    def removeEventFilter(self, obj):
        super().removeEventFilter(obj)
        self._window_container.removeEventFilter(obj)
        self._canvas_window.removeEventFilter(obj)

    def setCursor(self, cursor):
        super().setCursor(cursor)
        self._window_container.setCursor(cursor)

    def unsetCursor(self):
        super().unsetCursor()
        self._window_container.unsetCursor()

    def update(self):
        super().update()
        self._window_container.update()
        self._canvas_window.update()

    def setPalette(self, palette):
        super().setPalette(palette)
        self._sync_native_background()

    def _sync_native_background(self):
        palette = self.palette()
        self._window_container.setPalette(palette)
        bg = palette.color(QPalette.ColorRole.Window)
        if not bg.isValid():
            bg = palette.color(QPalette.ColorRole.Base)
        if not bg.isValid():
            bg = QColor(245, 245, 245)
        if hasattr(self._canvas_window, "setColor"):
            self._canvas_window.setColor(QColor(bg))

    def setFormat(self, fmt):
        self._canvas_window.setFormat(fmt)

    def context(self):
        return self._canvas_window.context()

    def makeCurrent(self):
        self._canvas_window.makeCurrent()

    def doneCurrent(self):
        self._canvas_window.doneCurrent()

    def defaultFramebufferObject(self):
        return self._canvas_window.defaultFramebufferObject()

    def grabFramebuffer(self):
        return self._canvas_window.grabFramebuffer()

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
        state._render_scene = build_gl_render_scene(
            state._store, apply_channel_mode_in_shader=state._apply_channel_mode_in_shader
        )
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
        shader_letterbox: bool = False,
    ):
        return upload_pil_images(
            self,
            pil_image1,
            pil_image2,
            source_image1,
            source_image2,
            source_key,
            shader_letterbox,
        )

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

    def set_magnifier_content(self, pixmap: QPixmap | None, top_left: QPoint | None):
        return set_magnifier_content(self, pixmap, top_left)

    def get_letterbox_params(self, slot: int = 0) -> tuple:
        return get_letterbox_params(self, slot)

    def set_magnifier_gpu_params(
        self,
        slots: list[dict | None],
        channel_mode: int = 0,
        diff_mode: int = 0,
        diff_threshold: float = 20.0 / 255.0,
        border_color: QColor | None = None,
        border_width: float = 2.0,
        interp_mode: int = 1,
    ):
        return set_magnifier_gpu_params(
            self, slots, channel_mode, diff_mode, diff_threshold, border_color, border_width, interp_mode
        )

    def _set_texture_filter(self, texture_id: int, gl_filter: int):
        return set_texture_filter(self, texture_id, gl_filter)

    def clear_magnifier_gpu(self):
        return clear_magnifier_gpu(self)

    def upload_magnifier_crop(
        self,
        pil_image,
        center: QPointF,
        radius: float,
        border_color: QColor | None = None,
        border_width: float = 2.0,
        index: int = 0,
        gl_filter: int = None,
    ):
        return upload_magnifier_crop(
            self, pil_image, center, radius, border_color, border_width, index, gl_filter
        )

    def upload_combined_magnifier(
        self,
        pil1,
        pil2,
        center: QPointF,
        radius: float,
        split: float = 0.5,
        horizontal: bool = False,
        divider_visible: bool = True,
        divider_color: tuple = (1.0, 1.0, 1.0, 0.9),
        divider_thickness: int = 2,
        border_color: QColor | None = None,
        border_width: float = 2.0,
        index: int = 0,
        gl_filter: int = None,
    ):
        return upload_combined_magnifier(
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
        mag_centers: list[QPointF],
        mag_radius: float,
    ):
        set_overlay_coords_impl(self, capture_center, capture_radius, mag_centers, mag_radius)

    def set_split_line_params(
        self,
        visible: bool,
        pos: int,
        is_horizontal: bool,
        color: QColor,
        thickness: int,
    ):
        set_split_line_params_impl(self, visible, pos, is_horizontal, color, thickness)

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
        magnifier: QPixmap | None,
        mag_pos: QPoint | None,
        coords_snapshot: tuple | None = None,
    ):
        return set_layers(self, background, magnifier, mag_pos, coords_snapshot)

    def set_pil_layers(
        self,
        pil_image1=None,
        pil_image2=None,
        magnifier=None,
        mag_pos=None,
        source_image1=None,
        source_image2=None,
        source_key=None,
        shader_letterbox: bool = False,
    ):
        return set_pil_layers(
            self,
            pil_image1,
            pil_image2,
            magnifier,
            mag_pos,
            source_image1,
            source_image2,
            source_key,
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

    def _update_split_for_zoom(self, new_zoom, new_pan_x, new_pan_y):
        update_split_for_zoom(self, new_zoom, new_pan_x, new_pan_y)

    def set_zoom(self, zoom: float):
        set_zoom_impl(self, zoom)

    def set_pan(self, x: float, y: float):
        set_pan_impl(self, x, y)

    def reset_view(self):
        reset_view_impl(self)
