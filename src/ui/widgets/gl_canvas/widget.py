import logging

import numpy as np
from OpenGL import GL as gl
from PIL import Image as PilImage
from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPixmap, QSurfaceFormat
from PyQt6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLVertexArrayObject,
)
from PyQt6.QtOpenGLWidgets import QOpenGLWidget

from .shaders import (
    BASE_FRAGMENT_SHADER,
    BASE_VERTEX_SHADER,
    CIRCLE_FRAGMENT_SHADER,
    CIRCLE_VERTEX_SHADER,
    MAGNIFIER_FRAGMENT_SHADER,
    MAGNIFIER_VERTEX_SHADER,
)
from .render import paint_gl
from .state import init_widget_state
from .textures import (
    clear as clear_textures_and_layers,
    clear_magnifier_gpu,
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
    upload_image,
    upload_magnifier_crop,
    upload_pil_images,
    upload_source_pil_image,
    update_letterbox_geometry,
)

logger = logging.getLogger("ImproveImgSLI")

class GLCanvas(QOpenGLWidget):
    mousePressed = pyqtSignal(object)
    mouseMoved = pyqtSignal(object)
    mouseReleased = pyqtSignal(object)
    wheelScrolled = pyqtSignal(object)
    zoomChanged = pyqtSignal(float)
    keyPressed = pyqtSignal(object)
    keyReleased = pyqtSignal(object)
    pasteOverlayDirectionSelected = pyqtSignal(str)
    pasteOverlayCancelled = pyqtSignal()

    _alignment = Qt.AlignmentFlag.AlignCenter

    def __init__(self, parent=None):
        super().__init__(parent)
        init_widget_state(self)

    def set_store(self, store):
        self._store = store
        store.on_change(lambda scope: self.update())

    def set_apply_channel_mode_in_shader(self, enabled: bool):
        self._apply_channel_mode_in_shader = enabled
        self.update()

    def set_drag_overlay_state(
        self,
        visible: bool,
        horizontal: bool = False,
        text1: str = "",
        text2: str = "",
    ):
        visible = bool(visible)
        new_texts = (text1, text2)
        if (
            self._drag_overlay_visible == visible
            and self._drag_overlay_horizontal == horizontal
            and self._drag_overlay_texts == new_texts
        ):
            return

        self._drag_overlay_visible = visible
        self._drag_overlay_horizontal = horizontal
        self._drag_overlay_texts = new_texts
        self._drag_overlay_cache_key = None
        self._drag_overlay_cached_image = None
        self.update()

    def is_drag_overlay_visible(self) -> bool:
        return bool(self._drag_overlay_visible)

    def resizeEvent(self, event):
        self._drag_overlay_cache_key = None
        self._drag_overlay_cached_image = None
        super().resizeEvent(event)

    def _update_paste_overlay_rects(self):
        width = float(self.width())
        height = float(self.height())
        if width <= 0 or height <= 0:
            return

        center_x = width / 2.0
        center_y = height / 2.0
        button_size = self._paste_overlay_button_size
        spacing = self._paste_overlay_spacing
        center_size = self._paste_overlay_center_size

        empty = QRectF()
        self._paste_overlay_rects["up"] = empty
        self._paste_overlay_rects["down"] = empty
        self._paste_overlay_rects["left"] = empty
        self._paste_overlay_rects["right"] = empty

        if self._paste_overlay_horizontal:
            self._paste_overlay_rects["up"] = QRectF(
                center_x - button_size / 2.0,
                center_y - button_size - spacing / 2.0 - center_size / 2.0,
                button_size,
                button_size,
            )
            self._paste_overlay_rects["down"] = QRectF(
                center_x - button_size / 2.0,
                center_y + spacing / 2.0 + center_size / 2.0,
                button_size,
                button_size,
            )
        else:
            self._paste_overlay_rects["left"] = QRectF(
                center_x - button_size - spacing / 2.0 - center_size / 2.0,
                center_y - button_size / 2.0,
                button_size,
                button_size,
            )
            self._paste_overlay_rects["right"] = QRectF(
                center_x + spacing / 2.0 + center_size / 2.0,
                center_y - button_size / 2.0,
                button_size,
                button_size,
            )

        self._paste_overlay_rects["cancel"] = QRectF(
            center_x - center_size / 2.0,
            center_y - center_size / 2.0,
            center_size,
            center_size,
        )

    def set_paste_overlay_state(
        self,
        visible: bool,
        is_horizontal: bool = False,
        texts: dict | None = None,
    ):
        self._paste_overlay_visible = visible
        self._paste_overlay_horizontal = is_horizontal
        if texts is not None:
            self._paste_overlay_texts = {
                "up": texts.get("up", ""),
                "down": texts.get("down", ""),
                "left": texts.get("left", ""),
                "right": texts.get("right", ""),
            }
        if not visible:
            self._paste_overlay_hovered_button = None
            self.unsetCursor()
        self._update_paste_overlay_rects()
        self.update()

    def is_paste_overlay_visible(self) -> bool:
        return bool(self._paste_overlay_visible)

    def _paste_overlay_button_at(self, pos: QPointF | QPoint) -> str | None:
        if not self._paste_overlay_visible:
            return None

        point = QPointF(pos)
        for direction in ("up", "down", "left", "right", "cancel"):
            rect = self._paste_overlay_rects.get(direction)
            if rect is not None and not rect.isNull() and rect.contains(point):
                return direction
        return None

    def _set_paste_overlay_hover(self, hovered: str | None):
        if self._paste_overlay_hovered_button == hovered:
            return
        self._paste_overlay_hovered_button = hovered
        if hovered is None:
            self.unsetCursor()
        else:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update()

    def initializeGL(self):
        self.shader_program = QOpenGLShaderProgram()
        if not self.shader_program.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit.Vertex, BASE_VERTEX_SHADER
        ):
            print(f"Vertex shader error: {self.shader_program.log()}")
        if not self.shader_program.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit.Fragment, BASE_FRAGMENT_SHADER
        ):
            print(f"Fragment shader error: {self.shader_program.log()}")
        self.shader_program.link()

        self.vao = QOpenGLVertexArrayObject()
        self.vao.create()
        self.vao.bind()

        self.vbo = QOpenGLBuffer()
        self.vbo.create()
        self.vbo.bind()
        self.vbo.allocate(self._quad_vertices.tobytes(), self._quad_vertices.nbytes)

        self.shader_program.enableAttributeArray(0)
        self.shader_program.setAttributeBuffer(0, gl.GL_FLOAT, 0, 2, 4 * 4)
        self.shader_program.enableAttributeArray(1)
        self.shader_program.setAttributeBuffer(1, gl.GL_FLOAT, 2 * 4, 2, 4 * 4)

        self.vbo.release()
        self.vao.release()

        self.texture_ids = list(gl.glGenTextures(2))
        self._source_texture_ids = list(gl.glGenTextures(2))

        for tex_id in self.texture_ids + self._source_texture_ids:
            gl.glBindTexture(gl.GL_TEXTURE_2D, tex_id)

            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)

            gl.glTexParameteri(
                gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE
            )
            gl.glTexParameteri(
                gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE
            )

        self._mag_shader = QOpenGLShaderProgram()
        self._mag_shader.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, MAGNIFIER_VERTEX_SHADER)
        self._mag_shader.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, MAGNIFIER_FRAGMENT_SHADER)
        self._mag_shader.link()

        tex_ids = list(gl.glGenTextures(3))
        self._mag_tex_id = int(tex_ids[0])
        self._mag_tex_ids = [int(t) for t in tex_ids]

        comb_tex_ids = list(gl.glGenTextures(3))
        self._mag_combined_tex_ids = [int(t) for t in comb_tex_ids]
        for tid in self._mag_tex_ids + self._mag_combined_tex_ids:
            gl.glBindTexture(gl.GL_TEXTURE_2D, tid)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)

        self._circle_mask_tex_id = int(gl.glGenTextures(1))
        gl.glBindTexture(gl.GL_TEXTURE_2D, self._circle_mask_tex_id)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)
        try:
            from utils.resource_loader import resource_path
            from PIL import Image as _PilImage
            from PyQt6.QtGui import QImage as _QImage
            _mask_img_raw = _PilImage.open(resource_path("resources/assets/circle_mask.png"))
            if "A" in _mask_img_raw.getbands():
                _mask_img = _mask_img_raw.getchannel("A")
            else:
                from PIL import ImageOps as _ImageOps
                _mask_img = _ImageOps.invert(_mask_img_raw.convert("L"))
            _mw, _mh = _mask_img.size
            _mask_raw = _mask_img.tobytes("raw", "L")
            gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RED, _mw, _mh, 0,
                            gl.GL_RED, gl.GL_UNSIGNED_BYTE, _mask_raw)
            _mask_rgba = _mask_img_raw.convert("RGBA")
            self._circle_mask_overlay_image = _QImage(
                _mask_rgba.tobytes("raw", "RGBA"),
                _mask_rgba.width,
                _mask_rgba.height,
                _QImage.Format.Format_RGBA8888,
            ).copy()
            _mask_shadow_rgba = _PilImage.new("RGBA", _mask_img.size, (0, 0, 0, 0))
            _mask_shadow_rgba.putalpha(_mask_img)
            self._circle_mask_shadow_image = _QImage(
                _mask_shadow_rgba.tobytes("raw", "RGBA"),
                _mask_shadow_rgba.width,
                _mask_shadow_rgba.height,
                _QImage.Format.Format_RGBA8888,
            ).copy()
            self._circle_mask_shadow_cache.clear()
        except Exception as _e:
            print(f"[GL] Failed to load circle_mask.png: {_e}")

        self._circle_shader = QOpenGLShaderProgram()
        self._circle_shader.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, CIRCLE_VERTEX_SHADER)
        self._circle_shader.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, CIRCLE_FRAGMENT_SHADER)
        self._circle_shader.link()

        self._guides_tex_id = int(gl.glGenTextures(1))
        gl.glBindTexture(gl.GL_TEXTURE_2D, self._guides_tex_id)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)

        self._ui_overlay_tex_id = int(gl.glGenTextures(1))
        gl.glBindTexture(gl.GL_TEXTURE_2D, self._ui_overlay_tex_id)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)

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

    def paintGL(self):
        return paint_gl(self)

    def resizeGL(self, w, h):
        gl.glViewport(0, 0, w, h)
        self._update_paste_overlay_rects()
        clear_magnifier_gpu(self)
        img1, img2 = self._stored_pil_images
        if self._shader_letterbox_mode and img1 is not None:
            update_letterbox_geometry(self, img1, slot_index=0)
        elif img1 is not None:
            self.upload_pil_images(
                img1,
                img2,
                source_image1=None,
                source_image2=None,
                source_key=None,
                shader_letterbox=False,
            )
            return
        if self._shader_letterbox_mode and img2 is not None:
            update_letterbox_geometry(self, img2, slot_index=1)
        elif img2 is not None:
            self._letterbox_params[1] = (0.0, 0.0, 1.0, 1.0)
        self.update()

    def _request_update(self):
        if self._update_batch_depth > 0:
            self._update_pending = True
            return
        self.update()

    def _schedule_source_preload(self):
        if self._source_preload_scheduled:
            return
        self._source_preload_scheduled = True
        QTimer.singleShot(0, self._preload_source_textures)

    def _preload_source_textures(self):
        self._source_preload_scheduled = False
        img1, img2 = self._source_pil_images
        if not img1 and not img2:
            self._source_images_ready = False
            return

        try:
            if img1 is not None:
                upload_source_pil_image(self, img1, 0)
            if img2 is not None:
                upload_source_pil_image(self, img2, 1)

            gl.glFinish()
            self._source_images_ready = True
            if self._store is not None and getattr(self._store.viewport, "use_magnifier", False):
                self._store.emit_state_change("viewport")
        except Exception:
            self._source_images_ready = False
            logger.exception("[GL-PRELOAD] failed ids=%s", getattr(self, "_source_image_ids", None))
        self._request_update()

    def begin_update_batch(self):
        self._update_batch_depth += 1

    def end_update_batch(self):
        if self._update_batch_depth <= 0:
            self._update_batch_depth = 0
            return
        self._update_batch_depth -= 1
        if self._update_batch_depth == 0 and self._update_pending:
            self._update_pending = False
            self.update()

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

    def upload_magnifier_crop(self, pil_image, center: QPointF, radius: float,
                               border_color: QColor | None = None, border_width: float = 2.0,
                               index: int = 0, gl_filter: int = None):
        return upload_magnifier_crop(
            self, pil_image, center, radius, border_color, border_width, index, gl_filter
        )

    def upload_combined_magnifier(self, pil1, pil2, center: QPointF, radius: float,
                                   split: float = 0.5, horizontal: bool = False,
                                   divider_visible: bool = True, divider_color: tuple = (1.0, 1.0, 1.0, 0.9),
                                   divider_thickness: int = 2,
                                   border_color: QColor | None = None, border_width: float = 2.0,
                                   index: int = 0, gl_filter: int = None):
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

    def set_overlay_coords(
        self,
        capture_center: QPointF | None,
        capture_radius: float,
        mag_centers: list[QPointF],
        mag_radius: float,
    ):
        self._capture_center = capture_center
        self._capture_radius = capture_radius
        self._magnifier_centers = mag_centers
        self._magnifier_radius = mag_radius
        if capture_center is None:
            self._mag_quads[0] = None
            self._mag_quads[1] = None
            self._mag_quads[2] = None
            self._mag_combined_params[0] = None
            self._mag_combined_params[1] = None
            self._mag_combined_params[2] = None
            self._mag_quad_ndc = None
        self._request_update()

    def set_split_line_params(
        self,
        visible: bool,
        pos: int,
        is_horizontal: bool,
        color: QColor,
        thickness: int,
    ):
        self._show_divider = visible
        self._split_pos = pos
        self._is_horizontal_split = is_horizontal
        self._divider_color = color
        self._divider_thickness = thickness

        self.is_horizontal = is_horizontal
        if visible and self._store is None:
            widget_size = self.width() if not is_horizontal else self.height()
            if widget_size > 0:
                self.split_position = pos / widget_size

        self._request_update()

    def set_guides_params(self, visible: bool, color: QColor, thickness: int):
        self._show_guides = visible
        self._laser_color = color
        self._guides_thickness = thickness
        self._request_update()

    def set_capture_color(self, color: QColor):
        self._capture_color = color
        self._request_update()

    def set_capture_area(
        self, center: QPoint | None, size: int, color: QColor | None = None
    ):
        if center:
            self._capture_center = QPointF(center)
        else:
            self._capture_center = None
        self._capture_radius = size / 2.0
        if color:
            self._capture_color = color
        self._request_update()

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

    def setAutoFillBackground(self, enabled):

        pass

    def setFocusPolicy(self, policy):
        super().setFocusPolicy(policy)

    def setAttribute(self, attribute, on=True):
        super().setAttribute(attribute, on)

    def contentsRect(self):
        return self.rect()

    def _update_split_for_zoom(self, new_zoom, new_pan_x, new_pan_y):
        store = self._store
        if store is None:
            return

        vp = store.viewport
        w, h = self.width(), self.height()
        img1 = self._stored_pil_images[0] if self._stored_pil_images else None
        if not img1 or w <= 0 or h <= 0:
            return

        ratio = min(w / img1.width, h / img1.height)
        nw = max(1, int(img1.width * ratio))
        nh = max(1, int(img1.height * ratio))
        img_x = (w - nw) // 2
        img_y = (h - nh) // 2

        if vp.is_horizontal:
            base = (img_y + nh * vp.split_position_visual) / h
            old_pan = self.pan_offset_y
        else:
            base = (img_x + nw * vp.split_position_visual) / w
            old_pan = self.pan_offset_x

        screen_pos = (base - 0.5 + old_pan) * self.zoom_level + 0.5

        new_pan = new_pan_y if vp.is_horizontal else new_pan_x
        new_base = (screen_pos - 0.5) / new_zoom + 0.5 - new_pan

        if vp.is_horizontal:
            new_split = (new_base * h - img_y) / nh if nh > 0 else 0.5
        else:
            new_split = (new_base * w - img_x) / nw if nw > 0 else 0.5

        new_split = max(0.0, min(1.0, new_split))
        vp.split_position = new_split
        vp.split_position_visual = new_split

    def set_zoom(self, zoom: float):
        new_zoom = max(1.0, min(zoom, 50.0))
        if abs(new_zoom - self.zoom_level) <= 1e-6:
            return
        self.zoom_level = new_zoom
        self.zoomChanged.emit(self.zoom_level)
        self.update()

    def set_pan(self, x: float, y: float):
        self.pan_offset_x = x
        self.pan_offset_y = y
        self.update()

    def reset_view(self):
        zoom_changed = abs(self.zoom_level - 1.0) > 1e-6
        self.zoom_level = 1.0
        self.pan_offset_x = 0.0
        self.pan_offset_y = 0.0
        if zoom_changed:
            self.zoomChanged.emit(self.zoom_level)
        self.update()

    def wheelEvent(self, event):
        modifiers = event.modifiers()

        if modifiers & Qt.KeyboardModifier.ControlModifier:
            angle = event.angleDelta().y()
            factor = 1.1 if angle > 0 else 0.9
            new_zoom = max(1.0, min(self.zoom_level * factor, 50.0))

            if new_zoom != self.zoom_level:
                w, h = self.width(), self.height()
                if w > 0 and h > 0:
                    mx = event.position().x() / w
                    my = event.position().y() / h

                    uv_x = (mx - 0.5) / self.zoom_level + 0.5 - self.pan_offset_x
                    uv_y = (my - 0.5) / self.zoom_level + 0.5 - self.pan_offset_y
                    uv_x = max(0.0, min(1.0, uv_x))
                    uv_y = max(0.0, min(1.0, uv_y))

                    new_pan_x = 0.5 - uv_x + (mx - 0.5) / new_zoom
                    new_pan_y = 0.5 - uv_y + (my - 0.5) / new_zoom

                    if new_zoom < 1.5:
                        t = max(0.0, (new_zoom - 1.0) / 0.5)
                        new_pan_x *= t
                        new_pan_y *= t

                    self._update_split_for_zoom(new_zoom, new_pan_x, new_pan_y)

                    self.pan_offset_x = new_pan_x
                    self.pan_offset_y = new_pan_y

                self.zoom_level = new_zoom
                self.zoomChanged.emit(self.zoom_level)
                self.update()

            event.accept()
        else:
            self.wheelScrolled.emit(event)

    def mousePressEvent(self, event):
        if self._paste_overlay_visible and event.button() == Qt.MouseButton.LeftButton:
            button = self._paste_overlay_button_at(event.position())
            if button == "cancel" or button is None:
                self.set_paste_overlay_state(False)
                self.pasteOverlayCancelled.emit()
            else:
                self.set_paste_overlay_state(False)
                self.pasteOverlayDirectionSelected.emit(button)
            event.accept()
            return
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_dragging = True
            self._pan_last_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        self.mousePressed.emit(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton and getattr(self, "_pan_dragging", False):
            self._pan_dragging = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        self.mouseReleased.emit(event)

    def mouseMoveEvent(self, event):
        if getattr(self, "_pan_dragging", False) and self.zoom_level > 1.0:
            w, h = self.width(), self.height()
            if w > 0 and h > 0:
                dx = (event.position().x() - self._pan_last_pos.x()) / (w * self.zoom_level)
                dy = (event.position().y() - self._pan_last_pos.y()) / (h * self.zoom_level)
                new_pan_x = self.pan_offset_x + dx
                new_pan_y = self.pan_offset_y + dy
                self._update_split_for_zoom(self.zoom_level, new_pan_x, new_pan_y)
                self.pan_offset_x = new_pan_x
                self.pan_offset_y = new_pan_y
                self._pan_last_pos = event.position()
                self.update()
            event.accept()
            return
        if self._paste_overlay_visible:
            self._set_paste_overlay_hover(self._paste_overlay_button_at(event.position()))
            event.accept()
            return
        self.mouseMoved.emit(event)

    def keyPressEvent(self, event):
        if self._paste_overlay_visible:
            key_to_direction = {
                Qt.Key.Key_Up: "up",
                Qt.Key.Key_W: "up",
                Qt.Key.Key_Down: "down",
                Qt.Key.Key_S: "down",
                Qt.Key.Key_Left: "left",
                Qt.Key.Key_A: "left",
                Qt.Key.Key_Right: "right",
                Qt.Key.Key_D: "right",
            }
            if event.key() == Qt.Key.Key_Escape:
                self.set_paste_overlay_state(False)
                self.pasteOverlayCancelled.emit()
                event.accept()
                return
            direction = key_to_direction.get(event.key())
            if direction and not self._paste_overlay_rects[direction].isNull():
                self.set_paste_overlay_state(False)
                self.pasteOverlayDirectionSelected.emit(direction)
                event.accept()
                return
        self.keyPressed.emit(event)

    def keyReleaseEvent(self, event):
        self.keyReleased.emit(event)

    def leaveEvent(self, event):
        if self._paste_overlay_visible:
            self._set_paste_overlay_hover(None)
        super().leaveEvent(event)
