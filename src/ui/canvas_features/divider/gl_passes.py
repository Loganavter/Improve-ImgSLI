from __future__ import annotations

from OpenGL import GL as gl
from PyQt6.QtGui import QColor
from PyQt6.QtOpenGL import QOpenGLShader, QOpenGLShaderProgram

from ui.canvas_infra.scene.gl_pass_contract import (
    CanvasGLRenderPass,
    SceneVisibility,
    is_single_image_preview_scene,
)
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole
from ui.canvas_infra.viewport.state import get_display_split_position
from ui.widgets.gl_canvas.render_common import widget_px_to_screen_px

_VERT = """
layout(location = 0) in vec2 aPos;
layout(location = 1) in vec2 aTexCoord;
out vec2 TexCoord;
void main() {
    gl_Position = vec4(aPos, 0.0, 1.0);
    TexCoord = aTexCoord;
}
"""

_FRAG = """
in vec2 TexCoord;
out vec4 FragColor;
uniform vec2 resolution;
uniform float positionPx;
uniform float halfThicknessPx;
uniform bool isHorizontal;
uniform vec4 color;
void main() {
    vec2 frag_px = TexCoord * resolution;
    float coord = isHorizontal ? frag_px.y : frag_px.x;
    float dist = abs(coord - positionPx);
    if (dist > max(0.5, halfThicknessPx)) discard;
    FragColor = color;
}
"""

def _prolog(is_gles: bool, *, fragment: bool = False) -> str:
    if not is_gles:
        return "#version 330 core"
    lines = ["#version 300 es", "precision highp float;", "precision highp int;"]
    if fragment:
        lines.append("precision mediump sampler2D;")
    return "\n".join(lines)

def _begin_screen_scissor(widget, rect: tuple[int, int, int, int] | None) -> bool:
    if rect is None:
        return False
    x, y, w, h = rect
    if w <= 0 or h <= 0:
        return False
    visible_left = max(0, x)
    visible_top = max(0, y)
    visible_right = min(widget.width(), x + w)
    visible_bottom = min(widget.height(), y + h)
    if visible_right <= visible_left or visible_bottom <= visible_top:
        return False
    dpr = widget.devicePixelRatio()
    physical_h = int(widget.height() * dpr)
    gl.glEnable(gl.GL_SCISSOR_TEST)
    gl.glScissor(
        int(visible_left * dpr),
        int(max(0, physical_h - int(visible_bottom * dpr))),
        int((visible_right - visible_left) * dpr),
        int((visible_bottom - visible_top) * dpr),
    )
    return True

def _divider_clip_rect_px(widget) -> tuple[int, int, int, int] | None:
    state = widget.runtime_state
    content_rect = state._content_rect_px
    if not content_rect:
        return None

    x, y, w, h = content_rect
    scene = state._render_scene
    clip_rect = getattr(scene, "overlay_clip_rect", None)
    img = state._stored_pil_images[0] if state._stored_pil_images else None

    if clip_rect and img is not None and getattr(img, "width", 0) > 0 and getattr(img, "height", 0) > 0:
        clip_x, clip_y, clip_w, clip_h = clip_rect
        x = x + int(round((clip_x / float(img.width)) * w))
        y = y + int(round((clip_y / float(img.height)) * h))
        w = int(round((clip_w / float(img.width)) * w))
        h = int(round((clip_h / float(img.height)) * h))

    x0, y0 = widget_px_to_screen_px(widget, x, y)
    x1, y1 = widget_px_to_screen_px(widget, x + w, y + h)
    left = int(round(min(x0, x1)))
    top = int(round(min(y0, y1)))
    width = max(0, int(round(abs(x1 - x0))))
    height = max(0, int(round(abs(y1 - y0))))
    return (left, top, width, height)

class DividerPass(CanvasGLRenderPass):
    stack_role = CanvasStackRole.UNDERLAY_SPLIT
    visibility = SceneVisibility.ALL

    @staticmethod
    def _resolve_divider_state(widget, ctx) -> tuple[bool, float, float, bool, QColor]:
        payloads = (
            ctx.scene_frame.feature_payloads
            if isinstance(getattr(ctx.scene_frame, "feature_payloads", None), dict)
            else {}
        )
        show_divider = bool(payloads.get("show_divider", False))
        thickness_px = float(payloads.get("divider_thickness", 0) or 0)
        color = QColor(payloads.get("divider_color", QColor(255, 255, 255, 255)))

        is_horizontal = bool(getattr(ctx.scene_frame, "is_horizontal", False))

        display_split = float(get_display_split_position(widget) or 0.5)
        position_px = (
            float(widget.height()) * display_split
            if is_horizontal
            else float(widget.width()) * display_split
        )

        return show_divider, position_px, thickness_px, is_horizontal, color

    def initialize(self, widget) -> None:
        is_gles = bool(widget.context().isOpenGLES())
        vert_src = f"{_prolog(is_gles)}\n{_VERT}"
        frag_src = f"{_prolog(is_gles, fragment=True)}\n{_FRAG}"
        self._shader = QOpenGLShaderProgram()
        ok_v = self._shader.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, vert_src)
        ok_f = self._shader.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, frag_src)
        linked = self._shader.link()
        if not (ok_v and ok_f and linked):
            import logging
            logging.getLogger("ImproveImgSLI").error(
                "DividerPass: shader compile/link failed: %s", self._shader.log()
            )
            self._shader = None

    def should_paint(self, ctx) -> bool:
        show_divider, _position_px, thickness_px, _is_horizontal, _color = self._resolve_divider_state(
            ctx.widget,
            ctx,
        )
        if is_single_image_preview_scene(ctx):
            return False
        images_uploaded = list(getattr(ctx, "images_uploaded", ()) or ())
        has_slot1 = bool(images_uploaded[0]) if len(images_uploaded) > 0 else False
        has_slot2 = bool(images_uploaded[1]) if len(images_uploaded) > 1 else False
        content_rect = getattr(ctx.scene_frame, "content_rect_px", None)
        has_content_rect = bool(
            content_rect is not None and len(content_rect) >= 4 and content_rect[2] > 0 and content_rect[3] > 0
        )
        return bool(
            show_divider
            and thickness_px > 0.0
            and has_slot1
            and has_slot2
            and has_content_rect
        )

    def paint(self, widget, ctx) -> None:
        if not self._shader or not self._shader.programId():
            return
        show_divider, position_px, thickness_px, is_horizontal, color = self._resolve_divider_state(
            widget,
            ctx,
        )
        if not show_divider or thickness_px <= 0.0:
            return

        scissor_enabled = _begin_screen_scissor(widget, _divider_clip_rect_px(widget))
        pid = self._shader.programId()
        self._shader.bind()
        widget.vao.bind()
        gl.glUniform2f(gl.glGetUniformLocation(pid, "resolution"), float(ctx.width), float(ctx.height))
        gl.glUniform1f(gl.glGetUniformLocation(pid, "positionPx"), position_px)
        gl.glUniform1f(gl.glGetUniformLocation(pid, "halfThicknessPx"), thickness_px * 0.5)
        gl.glUniform1i(gl.glGetUniformLocation(pid, "isHorizontal"), 1 if is_horizontal else 0)
        gl.glUniform4f(
            gl.glGetUniformLocation(pid, "color"),
            color.redF(),
            color.greenF(),
            color.blueF(),
            color.alphaF(),
        )
        gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)
        widget.vao.release()
        self._shader.release()
        if scissor_enabled:
            gl.glDisable(gl.GL_SCISSOR_TEST)

    def cleanup(self, widget) -> None:
        self._shader = None

GL_RENDER_PASSES: list[CanvasGLRenderPass] = [DividerPass()]
