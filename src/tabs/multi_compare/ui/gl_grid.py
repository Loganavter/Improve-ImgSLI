"""OpenGL grid widget for multi-compare — renders images via GPU with theme support."""

from __future__ import annotations

import ctypes
import logging
from typing import TYPE_CHECKING

import numpy as np
from OpenGL import GL as gl
from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QMouseEvent, QPalette, QWheelEvent
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import QWidget

from tabs.multi_compare.models import CompareSlot, MultiCompareState
from tabs.multi_compare.shaders import FRAGMENT_SHADER, VERTEX_SHADER
from ui.widgets.gl_canvas.runtime import build_canvas_surface_format

if TYPE_CHECKING:
    pass

logger = logging.getLogger("ImproveImgSLI")

class GLGridWidget(QOpenGLWidget):
    """GPU-accelerated grid that renders images with synchronized zoom/pan."""

    CELL_GAP = 2

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFormat(build_canvas_surface_format())

        self.state = MultiCompareState()
        self._textures: dict[int, int] = {}
        self._program = 0
        self._vao = 0
        self._vbo = 0
        self._initialized = False

        self._dragging = False
        self._drag_start = QPointF()
        self._pan_start = QPointF()

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_state(self, state: MultiCompareState) -> None:
        self.state = state
        self._sync_textures()
        self.update()

    def upload_image(self, slot: CompareSlot) -> None:
        """Upload or update a texture for a slot."""
        if not self._initialized or slot.image is None:
            return
        self.makeCurrent()
        tex = self._textures.get(slot.id)
        if tex is None:
            tex = gl.glGenTextures(1)
            self._textures[slot.id] = tex

        h, w = slot.image.shape[:2]
        channels = slot.image.shape[2] if slot.image.ndim == 3 else 1
        if channels == 4:
            fmt, internal = gl.GL_RGBA, gl.GL_RGBA8
        elif channels == 3:
            fmt, internal = gl.GL_RGB, gl.GL_RGB8
        else:
            fmt, internal = gl.GL_RED, gl.GL_R8

        gl.glBindTexture(gl.GL_TEXTURE_2D, tex)
        gl.glTexImage2D(
            gl.GL_TEXTURE_2D, 0, internal, w, h, 0,
            fmt, gl.GL_UNSIGNED_BYTE, slot.image.tobytes(),
        )
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)
        gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
        self.doneCurrent()

    def remove_texture(self, slot_id: int) -> None:
        tex = self._textures.pop(slot_id, None)
        if tex is not None and self._initialized:
            self.makeCurrent()
            gl.glDeleteTextures(1, [tex])
            self.doneCurrent()

    def initializeGL(self) -> None:
        self._program = self._compile_program()
        self._vao, self._vbo = self._create_quad()
        self._initialized = True
        self._sync_textures()

    def resizeGL(self, w: int, h: int) -> None:
        gl.glViewport(0, 0, w, h)

    def paintGL(self) -> None:
        self._clear_background()

        cells = self._cell_rects()
        if not cells:
            return

        gl.glUseProgram(self._program)
        gl.glBindVertexArray(self._vao)

        for slot, rect in cells:
            tex = self._textures.get(slot.id)
            if tex is None:
                continue
            self._draw_slot(slot, rect, tex)

        gl.glBindVertexArray(0)
        gl.glUseProgram(0)

    def _cell_rects(self) -> list[tuple[CompareSlot, QRect]]:
        slots = self.state.slots
        if not slots:
            return []

        if self.state.is_focused:
            slot = next(
                (s for s in slots if s.id == self.state.focused_slot_id), None
            )
            if slot:
                return [(slot, QRect(0, 0, self.width(), self.height()))]
            return []

        grid = self.state.grid
        w = self.width()
        h = self.height()
        gap = self.CELL_GAP

        cell_w = (w - gap * (grid.cols - 1)) // grid.cols
        cell_h = (h - gap * (grid.rows - 1)) // grid.rows

        result = []
        for i, slot in enumerate(slots):
            col = i % grid.cols
            row = i // grid.cols
            x = col * (cell_w + gap)
            y = row * (cell_h + gap)
            result.append((slot, QRect(x, y, cell_w, cell_h)))
        return result

    def _clear_background(self) -> None:
        bg = self.palette().color(QPalette.ColorRole.Window)
        if not bg.isValid():
            bg = QColor(30, 30, 30)
        gl.glClearColor(bg.redF(), bg.greenF(), bg.blueF(), 1.0)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT)

    def _draw_slot(self, slot: CompareSlot, rect: QRect, tex: int) -> None:
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        gl_y = h - rect.y() - rect.height()
        gl.glEnable(gl.GL_SCISSOR_TEST)
        gl.glScissor(rect.x(), gl_y, rect.width(), rect.height())
        gl.glViewport(rect.x(), gl_y, rect.width(), rect.height())

        loc_zoom = gl.glGetUniformLocation(self._program, "zoom")
        loc_pan = gl.glGetUniformLocation(self._program, "panOffset")
        loc_img = gl.glGetUniformLocation(self._program, "image")

        gl.glUniform1f(loc_zoom, self.state.zoom)
        gl.glUniform2f(loc_pan, self.state.pan_x / w, self.state.pan_y / h)
        gl.glUniform1i(loc_img, 0)

        gl.glActiveTexture(gl.GL_TEXTURE0)
        gl.glBindTexture(gl.GL_TEXTURE_2D, tex)

        gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)

        gl.glDisable(gl.GL_SCISSOR_TEST)
        gl.glViewport(0, 0, w, h)

    def _compile_program(self) -> int:
        vs = gl.glCreateShader(gl.GL_VERTEX_SHADER)
        gl.glShaderSource(vs, VERTEX_SHADER)
        gl.glCompileShader(vs)
        if not gl.glGetShaderiv(vs, gl.GL_COMPILE_STATUS):
            logger.error(f"Vertex shader error: {gl.glGetShaderInfoLog(vs)}")

        fs = gl.glCreateShader(gl.GL_FRAGMENT_SHADER)
        gl.glShaderSource(fs, FRAGMENT_SHADER)
        gl.glCompileShader(fs)
        if not gl.glGetShaderiv(fs, gl.GL_COMPILE_STATUS):
            logger.error(f"Fragment shader error: {gl.glGetShaderInfoLog(fs)}")

        prog = gl.glCreateProgram()
        gl.glAttachShader(prog, vs)
        gl.glAttachShader(prog, fs)
        gl.glLinkProgram(prog)
        if not gl.glGetProgramiv(prog, gl.GL_LINK_STATUS):
            logger.error(f"Program link error: {gl.glGetProgramInfoLog(prog)}")

        gl.glDeleteShader(vs)
        gl.glDeleteShader(fs)
        return prog

    def _create_quad(self) -> tuple[int, int]:

        vertices = np.array([

            -1.0, -1.0, 0.0, 1.0,
            +1.0, -1.0, 1.0, 1.0,
            -1.0, +1.0, 0.0, 0.0,
            +1.0, +1.0, 1.0, 0.0,
        ], dtype=np.float32)

        vao = gl.glGenVertexArrays(1)
        vbo = gl.glGenBuffers(1)

        gl.glBindVertexArray(vao)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, vbo)
        gl.glBufferData(gl.GL_ARRAY_BUFFER, vertices.nbytes, vertices, gl.GL_STATIC_DRAW)

        stride = 4 * 4
        gl.glEnableVertexAttribArray(0)
        gl.glVertexAttribPointer(0, 2, gl.GL_FLOAT, gl.GL_FALSE, stride, ctypes.c_void_p(0))
        gl.glEnableVertexAttribArray(1)
        gl.glVertexAttribPointer(1, 2, gl.GL_FLOAT, gl.GL_FALSE, stride, ctypes.c_void_p(8))

        gl.glBindVertexArray(0)
        return vao, vbo

    def _sync_textures(self) -> None:
        """Upload textures for any slots that don't have one yet."""
        if not self._initialized:
            return
        for slot in self.state.slots:
            if slot.id not in self._textures and slot.image is not None:
                self.upload_image(slot)

        active_ids = {s.id for s in self.state.slots}
        stale = [sid for sid in self._textures if sid not in active_ids]
        for sid in stale:
            self.remove_texture(sid)

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        factor = 1.1 if delta > 0 else 0.9
        self.state.zoom = max(0.1, min(50.0, self.state.zoom * factor))
        self.update()
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._dragging = True
            self._drag_start = event.position()
            self._pan_start = QPointF(self.state.pan_x, self.state.pan_y)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            delta = event.position() - self._drag_start
            self.state.pan_x = self._pan_start.x() + delta.x()
            self.state.pan_y = self._pan_start.y() + delta.y()
            self.update()
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton and self._dragging:
            self._dragging = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            for slot, rect in self._cell_rects():
                if rect.contains(pos):
                    if self.state.is_focused:
                        self.state.focused_slot_id = None
                    else:
                        self.state.focused_slot_id = slot.id
                    self.update()
                    break
            event.accept()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape and self.state.is_focused:
            self.state.focused_slot_id = None
            self.update()
            event.accept()
        elif key == Qt.Key.Key_0:
            self.state.zoom = 1.0
            self.state.pan_x = 0.0
            self.state.pan_y = 0.0
            self.update()
            event.accept()
        elif Qt.Key.Key_1 <= key <= Qt.Key.Key_9:
            index = key - Qt.Key.Key_1
            if index < len(self.state.slots):
                slot = self.state.slots[index]
                if self.state.focused_slot_id == slot.id:
                    self.state.focused_slot_id = None
                else:
                    self.state.focused_slot_id = slot.id
                self.update()
                event.accept()
        else:
            super().keyPressEvent(event)
