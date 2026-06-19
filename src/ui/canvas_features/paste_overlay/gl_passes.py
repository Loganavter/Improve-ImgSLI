from __future__ import annotations

import logging

from OpenGL import GL as gl
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtOpenGL import QOpenGLShader, QOpenGLShaderProgram

from ui.canvas_infra.scene.gl_pass_contract import CanvasGLRenderPass, SceneVisibility
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole
from ui.widgets.gl_canvas.render_metrics import resolve_screen_px
from ui.widgets.gl_canvas.render_common import new_overlay_image, upload_qimage_texture
from ui.widgets.gl_canvas.shader_sources.common import shader_prolog
from ui.widgets.gl_canvas.style_tokens import DEFAULT_CANVAS_STYLE_TOKENS

_log = logging.getLogger("ImproveImgSLI.paste_overlay")

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

def _draw_paste_button(
    painter: QPainter,
    rect: QRectF,
    text: str,
    hovered: bool,
    metrics,
) -> None:
    visual_width = resolve_screen_px(
        DEFAULT_CANVAS_STYLE_TOKENS.overlay_button_visual_width_du,
        metrics,
    )
    visual_height = resolve_screen_px(
        DEFAULT_CANVAS_STYLE_TOKENS.overlay_button_visual_height_du,
        metrics,
    )
    radius = resolve_screen_px(
        DEFAULT_CANVAS_STYLE_TOKENS.overlay_button_radius_du,
        metrics,
    )
    border_width = resolve_screen_px(
        DEFAULT_CANVAS_STYLE_TOKENS.overlay_button_border_hover_du
        if hovered
        else DEFAULT_CANVAS_STYLE_TOKENS.overlay_button_border_du,
        metrics,
    )
    center = rect.center()
    visual_rect = QRectF(
        center.x() - (visual_width / 2.0),
        center.y() - (visual_height / 2.0),
        visual_width,
        visual_height,
    )

    if hovered:
        bg_color = QColor(255, 255, 255, 22)
        text_color = QColor(255, 255, 255)
        border_color = QColor(100, 150, 255)
    else:
        bg_color = QColor(255, 255, 255, 10)
        text_color = QColor(248, 248, 248)
        border_color = QColor(255, 255, 255, 96)

    painter.setPen(QPen(border_color, border_width))
    painter.setBrush(bg_color)
    painter.drawRoundedRect(visual_rect, radius, radius)

    font = QFont(painter.font())
    font.setPixelSize(max(
        1,
        int(round(resolve_screen_px(
            DEFAULT_CANVAS_STYLE_TOKENS.overlay_button_font_hover_base_du
            if hovered
            else DEFAULT_CANVAS_STYLE_TOKENS.overlay_button_font_base_du,
            metrics,
        )))
    ))
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    font.setBold(hovered)
    painter.setFont(font)
    painter.setPen(text_color)
    painter.drawText(visual_rect, Qt.AlignmentFlag.AlignCenter, text)

def _draw_paste_overlay(painter: QPainter, widget, metrics) -> None:
    state = widget.runtime_state
    width = widget.width()
    height = widget.height()
    if width <= 0 or height <= 0:
        return

    backdrop_alpha = max(
        0,
        min(
            255,
            int(round(DEFAULT_CANVAS_STYLE_TOKENS.overlay_backdrop_alpha)),
        ),
    )
    painter.fillRect(0, 0, width, height, QColor(0, 0, 0, backdrop_alpha))

    buttons = []
    texts = state._paste_overlay_texts
    rects = state._paste_overlay_rects
    if not rects["up"].isNull():
        buttons.append(("up", rects["up"], texts.get("up", "")))
    if not rects["down"].isNull():
        buttons.append(("down", rects["down"], texts.get("down", "")))
    if not rects["left"].isNull():
        buttons.append(("left", rects["left"], texts.get("left", "")))
    if not rects["right"].isNull():
        buttons.append(("right", rects["right"], texts.get("right", "")))

    for direction, rect, text in buttons:
        _draw_paste_button(
            painter,
            rect,
            text,
            state._paste_overlay_hovered_button == direction,
            metrics,
        )

    cancel_rect = rects["cancel"]
    if cancel_rect.isNull():
        return
    is_cancel_hovered = state._paste_overlay_hovered_button == "cancel"
    cancel_stroke = resolve_screen_px(
        DEFAULT_CANVAS_STYLE_TOKENS.overlay_cancel_stroke_du,
        metrics,
    )
    cancel_icon = resolve_screen_px(
        DEFAULT_CANVAS_STYLE_TOKENS.overlay_cancel_icon_du,
        metrics,
    )
    cancel_bg = (
        QColor(220, 220, 220, 200)
        if is_cancel_hovered
        else QColor(180, 180, 180, 150)
    )
    painter.setPen(QPen(QColor(100, 100, 100), cancel_stroke))
    painter.setBrush(cancel_bg)
    painter.drawEllipse(cancel_rect)

    painter.setPen(QPen(QColor(80, 80, 80), cancel_stroke))
    center = cancel_rect.center()
    painter.drawLine(
        int(center.x() - cancel_icon),
        int(center.y() - cancel_icon),
        int(center.x() + cancel_icon),
        int(center.y() + cancel_icon),
    )
    painter.drawLine(
        int(center.x() - cancel_icon),
        int(center.y() + cancel_icon),
        int(center.x() + cancel_icon),
        int(center.y() - cancel_icon),
    )

def build_ui_overlay_image(widget, metrics) -> QImage | None:
    state = widget.runtime_state
    width = int(widget.width())
    height = int(widget.height())
    if width <= 0 or height <= 0:
        return None
    if not state._paste_overlay_visible:
        return None

    dpr = max(1.0, float(widget.devicePixelRatioF()))
    image = new_overlay_image(max(1, int(round(width * dpr))), max(1, int(round(height * dpr))))
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.scale(dpr, dpr)
        _draw_paste_overlay(painter, widget, metrics)
    finally:
        painter.end()
    return image

class PasteOverlayPass(CanvasGLRenderPass):
    stack_role = CanvasStackRole.TRANSIENT_PREVIEW
    visibility = SceneVisibility.INTERACTIVE
    def __init__(self):
        self._shader: QOpenGLShaderProgram | None = None
        self._tex_id: int = 0

    def initialize(self, widget) -> None:
        is_gles = bool(widget.context().isOpenGLES())
        self._shader = QOpenGLShaderProgram()
        self._shader.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit.Vertex,
            shader_prolog(is_gles) + "\n" + _VERT_SRC,
        )
        self._shader.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit.Fragment,
            shader_prolog(is_gles, fragment=True) + "\n" + _FRAG_SRC,
        )
        linked = self._shader.link()
        if not linked:
            _log.error("Paste overlay shader link failed: %s", self._shader.log())
        self._tex_id = int(gl.glGenTextures(1))
        gl.glBindTexture(gl.GL_TEXTURE_2D, self._tex_id)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)

    def should_paint(self, ctx) -> bool:
        state = getattr(ctx.widget, "runtime_state", None)
        if state is None:
            return False
        drag_visible = bool(getattr(state, "_drag_overlay_visible", False))
        paste_visible = bool(getattr(state, "_paste_overlay_visible", False))
        if drag_visible:
            _log.debug(
                "paste_overlay: drag overlay state is still active; skipping drag visuals text=%s horizontal=%s",
                getattr(state, "_drag_overlay_texts", ("", "")),
                bool(getattr(state, "_drag_overlay_horizontal", False)),
            )
        if paste_visible:
            _log.debug(
                "paste_overlay: visible hovered=%s texts=%s rects=%s visual_size=(%.1f, %.1f)",
                getattr(state, "_paste_overlay_hovered_button", None),
                dict(getattr(state, "_paste_overlay_texts", {})),
                {
                    key: (
                        round(rect.x(), 2),
                        round(rect.y(), 2),
                        round(rect.width(), 2),
                        round(rect.height(), 2),
                    )
                    for key, rect in getattr(state, "_paste_overlay_rects", {}).items()
                },
                resolve_screen_px(
                    DEFAULT_CANVAS_STYLE_TOKENS.overlay_button_visual_width_du,
                    ctx.metrics.render_metrics,
                ),
                resolve_screen_px(
                    DEFAULT_CANVAS_STYLE_TOKENS.overlay_button_visual_height_du,
                    ctx.metrics.render_metrics,
                ),
            )
        return paste_visible

    def paint(self, widget, ctx) -> None:
        if self._shader is None or not self._shader.programId() or not self._tex_id:
            return
        overlay = build_ui_overlay_image(widget, ctx.metrics.render_metrics)
        if overlay is None or overlay.isNull():
            return
        if not upload_qimage_texture(self._tex_id, overlay):
            return

        gl.glDisable(gl.GL_SCISSOR_TEST)
        gl.glViewport(0, 0, max(1, widget.width()), max(1, widget.height()))
        gl.glEnable(gl.GL_BLEND)
        gl.glBlendFunc(gl.GL_ONE, gl.GL_ONE_MINUS_SRC_ALPHA)

        self._shader.bind()
        widget.vao.bind()
        self._shader.setUniformValue("uTex", 0)
        gl.glActiveTexture(gl.GL_TEXTURE0)
        gl.glBindTexture(gl.GL_TEXTURE_2D, self._tex_id)
        gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)
        widget.vao.release()
        self._shader.release()

    def cleanup(self, widget) -> None:
        if self._tex_id:
            gl.glDeleteTextures(1, [self._tex_id])
            self._tex_id = 0
        self._shader = None

GL_RENDER_PASSES = [PasteOverlayPass()]
