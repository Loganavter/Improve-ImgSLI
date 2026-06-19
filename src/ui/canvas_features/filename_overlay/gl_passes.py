from __future__ import annotations

import ctypes

import numpy as np
from OpenGL import GL as gl
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtOpenGL import QOpenGLShader, QOpenGLShaderProgram, QOpenGLVertexArrayObject

from ui.canvas_infra.scene.gl_pass_contract import CanvasGLRenderPass, SceneVisibility
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole
from ui.canvas_presentation.render_arch import FilenameOverlayStyle
from ui.canvas_features.filename_overlay.labels import (
    draw_round_rect,
    draw_text_bold_supersampled,
    fit_text,
    font_for_style,
    label_rects,
    limit_name,
    qcolor,
    snap_rect_to_pixels,
)
from ui.canvas_features.filename_overlay.shaders import FRAG_SRC, VERT_SRC
from ui.widgets.gl_canvas.render_common import new_overlay_image, upload_qimage_texture
from ui.widgets.gl_canvas.shader_sources.common import shader_prolog

class FilenameOverlayPass(CanvasGLRenderPass):
    """
    Renders filename labels as screen-space quads using per-label textures.

    Each label is CPU-rasterized (QPainter → QImage) into a small texture
    whose dimensions match just the label, then drawn as a positioned
    TRIANGLE_STRIP quad in NDC space.  Because the quad coordinates are
    computed from widget-pixel positions (not image-UV), the labels stay at
    a fixed screen position independent of zoom and pan.
    """

    stack_role = CanvasStackRole.HUD_LABEL
    visibility = SceneVisibility.ALL
    def __init__(self):
        self._shader: QOpenGLShaderProgram | None = None
        self._vao: QOpenGLVertexArrayObject | None = None
        self._vbo_id: int = 0
        self._tex_ids: list[int] = [0, 0]

        self._cache_keys: list[object] = [None, None]

    def initialize(self, widget) -> None:
        is_gles = widget.context().isOpenGLES()
        prolog_v = shader_prolog(is_gles)
        prolog_f = shader_prolog(is_gles, fragment=True)

        self._shader = QOpenGLShaderProgram()
        self._shader.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit.Vertex,
            prolog_v + "\n" + VERT_SRC,
        )
        self._shader.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit.Fragment,
            prolog_f + "\n" + FRAG_SRC,
        )
        self._shader.link()

        self._vao = QOpenGLVertexArrayObject()
        self._vao.create()
        self._vao.bind()

        self._vbo_id = int(gl.glGenBuffers(1))
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self._vbo_id)

        gl.glBufferData(gl.GL_ARRAY_BUFFER, 4 * 4 * 4, None, gl.GL_DYNAMIC_DRAW)

        stride = 4 * 4
        gl.glEnableVertexAttribArray(0)
        gl.glVertexAttribPointer(0, 2, gl.GL_FLOAT, gl.GL_FALSE, stride, None)
        gl.glEnableVertexAttribArray(1)
        gl.glVertexAttribPointer(
            1, 2, gl.GL_FLOAT, gl.GL_FALSE, stride, ctypes.c_void_p(8)
        )

        self._vao.release()

        self._tex_ids = list(gl.glGenTextures(2))
        for tex_id in self._tex_ids:
            gl.glBindTexture(gl.GL_TEXTURE_2D, tex_id)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)

    def should_paint(self, ctx) -> bool:
        cfg = (
            ctx.scene_frame.feature_payloads.get("filename_overlay")
            if isinstance(ctx.scene_frame.feature_payloads, dict)
            else None
        )
        if cfg is None:
            return False
        single_preview = int(getattr(ctx.scene_frame, "single_image_preview", 0) or 0)
        if not bool(getattr(cfg, "enabled", False)) and single_preview == 0:
            return False
        images_uploaded = list(getattr(ctx, "images_uploaded", ()) or ())
        has_slot1 = bool(images_uploaded[0]) if len(images_uploaded) > 0 else False
        has_slot2 = bool(images_uploaded[1]) if len(images_uploaded) > 1 else False
        raw_name1 = str(getattr(cfg, "name1", "") or "").strip()
        raw_name2 = str(getattr(cfg, "name2", "") or "").strip()
        if single_preview == 1:
            if not has_slot1 or not raw_name1:
                return False
        elif single_preview == 2:
            if not has_slot2 or not raw_name2:
                return False
        else:
            if not (has_slot1 and has_slot2):
                return False
            if not (raw_name1 or raw_name2):
                return False
        render_mode = str(
            getattr(getattr(ctx, "render_metrics", None), "mode", "") or ""
        )
        zoom = float(getattr(ctx, "zoom_level", 1.0) or 1.0)
        if render_mode == "interactive" and single_preview == 0 and zoom > 1.0 + 1e-6:
            return False
        return ctx.width > 0 and ctx.height > 0

    def paint(self, widget, ctx) -> None:
        if not self._shader or not self._vao or not self._vbo_id:
            return
        if not self._shader.programId():
            return

        cfg = (
            ctx.scene_frame.feature_payloads.get("filename_overlay")
            if isinstance(ctx.scene_frame.feature_payloads, dict)
            else None
        )
        if cfg is None:
            return

        content_rect = ctx.scene_frame.image_rect_px
        split_override = ctx.scene_frame.split_override
        if content_rect is None:
            return
        zoom = float(getattr(ctx, "zoom_level", 1.0) or 1.0)
        pan_x = float(getattr(ctx, "pan_offset_x", 0.0) or 0.0)
        pan_y = float(getattr(ctx, "pan_offset_y", 0.0) or 0.0)
        single_preview = int(getattr(ctx.scene_frame, "single_image_preview", 0) or 0)
        render_mode = str(
            getattr(getattr(ctx, "render_metrics", None), "mode", "") or ""
        )
        is_interactive_live = render_mode == "interactive"
        image_anchored = not (single_preview != 0 and is_interactive_live)

        apply_transform = image_anchored and (
            abs(zoom - 1.0) > 1e-6 or abs(pan_x) > 1e-9 or abs(pan_y) > 1e-9
        )
        wcx = ctx.width / 2.0
        wcy = ctx.height / 2.0

        def _to_screen_rect(r: QRectF) -> QRectF:
            if not apply_transform:
                return r
            left = wcx + (r.left() - wcx) * zoom + pan_x * float(ctx.width)
            top = wcy + (r.top() - wcy) * zoom + pan_y * float(ctx.height)
            return QRectF(left, top, r.width() * zoom, r.height() * zoom)

        name1 = str(getattr(cfg, "name1", "") or "")
        name2 = str(getattr(cfg, "name2", "") or "")
        divider_thickness_px = float(
            (
                ctx.scene_frame.feature_payloads.get("filename_divider_thickness", 0)
                if isinstance(ctx.scene_frame.feature_payloads, dict)
                else 0
            )
            or 0
        )

        if content_rect[2] <= 0 or content_rect[3] <= 0:
            return

        max_name_length = int(getattr(cfg, "max_name_length", 50))
        if single_preview == 1:
            name1 = limit_name(name1, max_name_length)
            name2 = ""
        elif single_preview == 2:
            name1 = ""
            name2 = limit_name(name2, max_name_length)
        else:
            name1 = limit_name(name1, max_name_length)
            name2 = limit_name(name2, max_name_length)

        overlay_style = ctx.resolved_style.filename_overlay

        font = font_for_style(widget, overlay_style)
        font_metrics = QFontMetrics(font)
        if single_preview == 1:
            split_override = 1.0
        elif single_preview == 2:
            split_override = 0.0
        rect1, rect2 = label_rects(
            cfg, content_rect, font_metrics, name1, name2, overlay_style, split_override,
            divider_thickness_wx=divider_thickness_px,
        )
        rect1 = snap_rect_to_pixels(rect1)
        rect2 = snap_rect_to_pixels(rect2)

        text_color = qcolor(getattr(cfg, "file_name_color", None), QColor(255, 0, 0, 255))
        raw_alpha = max(0, min(255, int(text_color.alpha() * overlay_style.text_alpha)))
        text_color.setAlpha(raw_alpha)
        bg_color = qcolor(getattr(cfg, "file_name_bg_color", None), QColor(0, 0, 0, 80))
        bg_color.setAlpha(
            max(0, min(255, int(bg_color.alpha() * overlay_style.text_alpha)))
        )
        draw_bg = bool(getattr(cfg, "draw_text_background", True))

        font_key = (
            int(overlay_style.font_pixel_size),
            int(getattr(cfg, "font_weight", 0) or 0),
            text_color.rgba(),
            bg_color.rgba(),
            draw_bg,
        )

        gl.glEnable(gl.GL_BLEND)
        gl.glBlendFunc(gl.GL_ONE, gl.GL_ONE_MINUS_SRC_ALPHA)

        for i, (name, rect) in enumerate([(name1, rect1), (name2, rect2)]):
            if not name or rect is None:
                self._cache_keys[i] = None
                continue

            rw = max(1, int(rect.width()))
            rh = max(1, int(rect.height()))
            dpr = max(1.0, float(widget.devicePixelRatioF()))
            cache_key = (name, rw, rh, font_key, round(dpr, 3))

            font_weight = int(getattr(cfg, "font_weight", 0) or 0)
            if self._cache_keys[i] != cache_key:
                self._rasterize_label(
                    i, name, rw, rh, font, font_metrics, text_color, bg_color,
                    draw_bg, overlay_style, font_weight, dpr,
                )
                self._cache_keys[i] = cache_key

            self._draw_label_quad(
                ctx, _to_screen_rect(rect), self._tex_ids[i], smooth=apply_transform
            )

    def cleanup(self, widget) -> None:
        self._cache_keys = [None, None]
        if self._tex_ids:
            valid = [t for t in self._tex_ids if t]
            if valid:
                gl.glDeleteTextures(len(valid), valid)
            self._tex_ids = [0, 0]
        if self._vbo_id:
            gl.glDeleteBuffers(1, [self._vbo_id])
            self._vbo_id = 0
        if self._vao is not None:
            self._vao.destroy()
            self._vao = None
        self._shader = None

    def _rasterize_label(
        self,
        slot: int,
        name: str,
        rw: int,
        rh: int,
        font: QFont,
        metrics: QFontMetrics,
        text_color: QColor,
        bg_color: QColor,
        draw_bg: bool,
        style: FilenameOverlayStyle,
        font_weight: int = 0,
        dpr: float = 1.0,
    ) -> None:
        dpr = max(1.0, float(dpr))
        phys_w = max(1, int(round(rw * dpr)))
        phys_h = max(1, int(round(rh * dpr)))
        img = new_overlay_image(phys_w, phys_h)
        painter = QPainter(img)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            painter.scale(dpr, dpr)
            painter.setFont(font)
            label_rect = QRectF(0.0, 0.0, float(rw), float(rh))
            if draw_bg:
                draw_round_rect(
                    painter,
                    label_rect.adjusted(0.5, 0.5, -0.5, -0.5),
                    bg_color,
                    style,
                )
            text_inset = float(style.text_inset_px)
            text_str = fit_text(name, metrics, float(rw) - (text_inset * 2.0))
            if font_weight > 0:
                draw_text_bold_supersampled(
                    painter,
                    text_str,
                    font,
                    text_color,
                    font_weight,
                    rw,
                    rh,
                    text_inset,
                )
            else:
                painter.setPen(QPen(text_color))
                painter.drawText(
                    label_rect.adjusted(text_inset, 0.0, -text_inset, 0.0),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    text_str,
                )
        finally:
            painter.end()
        upload_qimage_texture(self._tex_ids[slot], img)

    def _draw_label_quad(self, ctx, rect: QRectF, tex_id: int, smooth: bool = False) -> None:
        """Upload quad vertices for *rect* (widget-pixel space) and draw."""
        w = float(ctx.width)
        h = float(ctx.height)

        x0 = rect.left()   / w * 2.0 - 1.0
        x1 = rect.right()  / w * 2.0 - 1.0
        y0 = 1.0 - rect.top()    / h * 2.0
        y1 = 1.0 - rect.bottom() / h * 2.0

        verts = np.array([
            x0, y0, 0.0, 0.0,
            x0, y1, 0.0, 1.0,
            x1, y0, 1.0, 0.0,
            x1, y1, 1.0, 1.0,
        ], dtype=np.float32)

        try:
            self._shader.bind()
            self._vao.bind()
            gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self._vbo_id)
            gl.glBufferSubData(gl.GL_ARRAY_BUFFER, 0, verts.nbytes, verts.tobytes())
            self._shader.setUniformValue("uTex", 0)
            gl.glActiveTexture(gl.GL_TEXTURE0)
            gl.glBindTexture(gl.GL_TEXTURE_2D, tex_id)
            filt = gl.GL_LINEAR if smooth else gl.GL_NEAREST
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, filt)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, filt)
            gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)
            self._vao.release()
            self._shader.release()
        except Exception:

            self._vbo_id = 0
            self._vao = None
            self._shader = None
            self._cache_keys = [None, None]

GL_RENDER_PASSES = [FilenameOverlayPass()]
