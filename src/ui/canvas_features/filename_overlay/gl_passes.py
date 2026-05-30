from __future__ import annotations

import ctypes
import logging

import numpy as np
from OpenGL import GL as gl
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPainterPath, QPen
from PyQt6.QtOpenGL import QOpenGLShader, QOpenGLShaderProgram, QOpenGLVertexArrayObject

from ui.canvas_infra.scene.gl_pass_contract import CanvasGLRenderPass, SceneVisibility
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole
from ui.canvas_presentation.render_arch import FilenameOverlayStyle
from ui.widgets.gl_canvas.render_common import new_overlay_image, upload_qimage_texture
from ui.widgets.gl_canvas.shader_sources.common import shader_prolog

_VERT_SRC = """
layout(location = 0) in vec2 aPos;
layout(location = 1) in vec2 aUV;
out vec2 vUV;
void main() {
    gl_Position = vec4(aPos, 0.0, 1.0);
    vUV = aUV;
}
"""

_FRAG_SRC = """
in vec2 vUV;
out vec4 FragColor;
uniform sampler2D uTex;
void main() {
    FragColor = texture(uTex, vUV);
}
"""

_mlog = logging.getLogger("ImproveImgSLI.video_magnifier_layout")

def _qcolor(value, fallback: QColor) -> QColor:
    if isinstance(value, QColor):
        return QColor(value)
    if value is not None and all(hasattr(value, attr) for attr in ("r", "g", "b", "a")):
        return QColor(int(value.r), int(value.g), int(value.b), int(value.a))
    return QColor(fallback)

def _font(widget, style: FilenameOverlayStyle) -> QFont:
    font = QFont(widget.font())
    font.setPixelSize(int(style.font_pixel_size))
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return font

def _snap_rect_to_pixels(rect: QRectF | None) -> QRectF | None:
    if rect is None:
        return None
    x = int(round(rect.left()))
    y = int(round(rect.top()))
    w = max(1, int(round(rect.width())))
    h = max(1, int(round(rect.height())))
    return QRectF(float(x), float(y), float(w), float(h))

def _label_rects(
    cfg,
    content_rect,
    font_metrics: QFontMetrics,
    name1: str,
    name2: str,
    style: FilenameOverlayStyle,
    split_override: float | None = None,
    divider_thickness_wx: float | None = None,
):
    x, y, w, h = content_rect
    safe_gap = float(style.label_safe_gap_px)
    padding_x = float(style.label_padding_x_px)
    padding_y = float(style.label_padding_y_px)
    glyph_overscan = float(style.glyph_overscan_px)
    label_h = float(font_metrics.height()) + padding_y * 2.0
    min_text_w = float(font_metrics.horizontalAdvance("..."))
    min_label_w = padding_x * 2.0 + min_text_w
    raw_split = split_override if split_override is not None else float(getattr(cfg, "split_position", 0.5))
    split = max(0.0, min(1.0, raw_split))
    is_horizontal = bool(getattr(cfg, "is_horizontal", False))
    placement = str(getattr(cfg, "text_placement_mode", "edges") or "edges")
    if divider_thickness_wx is not None:
        half_line = divider_thickness_wx / 2.0
    else:
        divider = max(0, int(getattr(cfg, "divider_thickness", 0) or 0))
        half_line = float((divider + 1) // 2)

    def rect_for(text: str, max_w: float, anchor_x: float, anchor_y: float, align: str):
        if not text or max_w < min_label_w:
            return None
        preferred_w = (
            float(font_metrics.horizontalAdvance(text))
            + padding_x * 2.0
            + glyph_overscan
        )
        text_w = max(1.0, min(max_w, preferred_w))
        if align == "right":
            left = anchor_x - text_w
        elif align == "center":
            left = anchor_x - (text_w / 2.0)
        else:
            left = anchor_x
        left = max(float(x), min(left, float(x + w) - text_w))
        top = max(float(y), min(anchor_y, float(y + h) - label_h))
        return QRectF(left, top, max(1.0, text_w), label_h)

    if is_horizontal:
        split_y = y + h * split
        max_w = max(1.0, float(w) - safe_gap * 2.0)
        if placement == "split_line":
            y1 = split_y - half_line - safe_gap - label_h
            y2 = split_y + half_line + safe_gap
        else:
            y1 = float(y) + safe_gap
            y2 = float(y + h) - safe_gap - label_h
        center_x = float(x) + (float(w) / 2.0)
        return (
            rect_for(name1, max_w, center_x, y1, "center"),
            rect_for(name2, max_w, center_x, y2, "center"),
        )

    split_x = x + w * split
    max_left = max(1.0, split_x - float(x) - half_line - safe_gap)
    max_right = max(1.0, float(x + w) - split_x - half_line - safe_gap)
    anchor_y = float(y + h) - safe_gap - label_h
    if placement == "split_line":
        return (
            rect_for(name1, max_left, split_x - half_line - safe_gap, anchor_y, "right"),
            rect_for(name2, max_right, split_x + half_line + safe_gap, anchor_y, "left"),
        )
    return (
        rect_for(name1, max_left - safe_gap, float(x) + safe_gap, anchor_y, "left"),
        rect_for(name2, max_right - safe_gap, float(x + w) - safe_gap, anchor_y, "right"),
    )

def _limit_name(text: str, max_name_length: int) -> str:
    if max_name_length <= 0 or len(text) <= max_name_length:
        return text
    return text[:max_name_length]

def _draw_round_rect(
    painter: QPainter,
    rect: QRectF,
    color: QColor,
    style: FilenameOverlayStyle,
) -> None:
    path = QPainterPath()
    radius = float(style.label_corner_radius_px)
    path.addRoundedRect(rect, radius, radius)
    painter.fillPath(path, color)

def _fit_text(text: str, font_metrics: QFontMetrics, available_width: float) -> str:
    if font_metrics.horizontalAdvance(text) <= int(available_width):
        return text
    return font_metrics.elidedText(
        text, Qt.TextElideMode.ElideRight, max(1, int(available_width))
    )

def _draw_text_bold_supersampled(
    painter: QPainter,
    text: str,
    font: QFont,
    color: QColor,
    font_weight: int,
    rw: int,
    rh: int,
    text_inset_px: float,
) -> None:
    from shared_toolkit.ui.managers.font_manager import FontManager

    pixel_size = font.pixelSize()
    scale = 4
    stroke_w = max(0, int((pixel_size / 1000.0) * font_weight * scale))
    fill_rgba = (color.red(), color.green(), color.blue(), color.alpha())
    font_path = FontManager.get_instance().get_current_font_path()

    if font_path:
        try:
            from PIL import Image, ImageDraw, ImageFont as PILImageFont

            pil_font = PILImageFont.truetype(font_path, pixel_size * scale)
            hr_bbox = pil_font.getbbox(text, stroke_width=stroke_w)
            hr_w = max(1, hr_bbox[2] - hr_bbox[0])
            hr_h = max(1, hr_bbox[3] - hr_bbox[1])
            txt_canvas = Image.new("RGBA", (hr_w, hr_h), (0, 0, 0, 0))
            ImageDraw.Draw(txt_canvas).text(
                (-hr_bbox[0], -hr_bbox[1]),
                text,
                fill=fill_rgba,
                font=pil_font,
                stroke_width=stroke_w,
                stroke_fill=fill_rgba,
            )
            final_w = max(1, hr_w // scale)
            final_h = max(1, hr_h // scale)
            txt_small = txt_canvas.resize((final_w, final_h), Image.Resampling.LANCZOS)
            raw = txt_small.tobytes("raw", "RGBA")
            txt_qimg = QImage(raw, final_w, final_h, final_w * 4, QImage.Format.Format_RGBA8888).copy()
            paste_x = float(text_inset_px)
            paste_y = float(max(0, (rh - final_h) // 2))
            painter.drawImage(QPointF(paste_x, paste_y), txt_qimg)
            return
        except Exception:
            pass

    big_w, big_h = rw * scale, rh * scale
    big_img = new_overlay_image(big_w, big_h)
    big_painter = QPainter(big_img)
    big_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    big_font = QFont(font)
    big_font.setPixelSize(pixel_size * scale)
    big_metrics = QFontMetrics(big_font)
    baseline_y = (float(big_h) - big_metrics.height()) / 2.0 + big_metrics.ascent()
    stroke_px_qt = float(pixel_size) * font_weight / 500.0 * scale
    path = QPainterPath()
    path.addText(QPointF(float(text_inset_px) * scale, baseline_y), big_font, text)
    pen = QPen(color, stroke_px_qt)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    big_painter.setPen(pen)
    big_painter.setBrush(color)
    big_painter.drawPath(path)
    big_painter.end()
    painter.drawImage(
        QRectF(0.0, 0.0, float(rw), float(rh)),
        big_img,
        QRectF(0.0, 0.0, float(big_w), float(big_h)),
    )

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
            prolog_v + "\n" + _VERT_SRC,
        )
        self._shader.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit.Fragment,
            prolog_f + "\n" + _FRAG_SRC,
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
            name1 = _limit_name(name1, max_name_length)
            name2 = ""
        elif single_preview == 2:
            name1 = ""
            name2 = _limit_name(name2, max_name_length)
        else:
            name1 = _limit_name(name1, max_name_length)
            name2 = _limit_name(name2, max_name_length)

        overlay_style = ctx.resolved_style.filename_overlay

        font = _font(widget, overlay_style)
        font_metrics = QFontMetrics(font)
        if single_preview == 1:
            split_override = 1.0
        elif single_preview == 2:
            split_override = 0.0
        rect1, rect2 = _label_rects(
            cfg, content_rect, font_metrics, name1, name2, overlay_style, split_override,
            divider_thickness_wx=divider_thickness_px,
        )
        rect1 = _snap_rect_to_pixels(rect1)
        rect2 = _snap_rect_to_pixels(rect2)

        text_color = _qcolor(getattr(cfg, "file_name_color", None), QColor(255, 0, 0, 255))
        raw_alpha = max(0, min(255, int(text_color.alpha() * overlay_style.text_alpha)))
        text_color.setAlpha(raw_alpha)
        bg_color = _qcolor(getattr(cfg, "file_name_bg_color", None), QColor(0, 0, 0, 80))
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
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)

        for i, (name, rect) in enumerate([(name1, rect1), (name2, rect2)]):
            if not name or rect is None:
                self._cache_keys[i] = None
                continue

            rw = max(1, int(rect.width()))
            rh = max(1, int(rect.height()))
            cache_key = (name, rw, rh, font_key)

            font_weight = int(getattr(cfg, "font_weight", 0) or 0)
            if self._cache_keys[i] != cache_key:
                self._rasterize_label(
                    i, name, rw, rh, font, font_metrics, text_color, bg_color,
                    draw_bg, overlay_style, font_weight,
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
    ) -> None:
        img = new_overlay_image(rw, rh)
        painter = QPainter(img)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            painter.setFont(font)
            label_rect = QRectF(0.0, 0.0, float(rw), float(rh))
            if draw_bg:
                _draw_round_rect(
                    painter,
                    label_rect.adjusted(0.5, 0.5, -0.5, -0.5),
                    bg_color,
                    style,
                )
            text_inset = float(style.text_inset_px)
            text_str = _fit_text(name, metrics, float(rw) - (text_inset * 2.0))
            if font_weight > 0:
                _draw_text_bold_supersampled(
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
