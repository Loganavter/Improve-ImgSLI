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
from ui.widgets.gl_canvas.render_config import begin_content_scissor, end_content_scissor
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
uniform vec2 center_px;
uniform float radius_px;
uniform float lineWidth_px;
uniform vec4 color;
void main() {
    vec2 frag_px = TexCoord * resolution;
    float dist = distance(frag_px, center_px);
    float half_w = max(0.5, lineWidth_px * 0.5);
    float aa = 1.15;
    float delta = abs(dist - radius_px);
    float solid_w = max(0.0, half_w - aa);
    float ring = 1.0 - smoothstep(solid_w, half_w + aa, delta);
    if (ring <= 0.01) discard;
    FragColor = vec4(color.rgb, color.a * ring);
}
"""

def _prolog(is_gles: bool, *, fragment: bool = False) -> str:
    if not is_gles:
        return "#version 330 core"
    lines = ["#version 300 es", "precision highp float;", "precision highp int;"]
    if fragment:
        lines.append("precision mediump sampler2D;")
    return "\n".join(lines)

class CaptureRingPass(CanvasGLRenderPass):
    """Draws capture-area rings for all visible magnifier instances."""

    stack_role = CanvasStackRole.ANNOTATION_RING
    visibility = SceneVisibility.ALL

    @staticmethod
    def _resolve_capture_circles(widget, ctx) -> tuple[tuple[object, float, object], ...]:
        payloads = (
            ctx.scene_frame.feature_payloads
            if isinstance(getattr(ctx.scene_frame, "feature_payloads", None), dict)
            else {}
        )
        circles = payloads.get("capture_circles")
        if circles:
            return tuple(circles)
        return tuple(getattr(widget.runtime_state, "_capture_circles", ()))

    def initialize(self, widget) -> None:
        is_gles = bool(widget.context().isOpenGLES())
        vert_src = f"{_prolog(is_gles)}\n{_VERT}"
        frag_src = f"{_prolog(is_gles, fragment=True)}\n{_FRAG}"

        self._shader = QOpenGLShaderProgram()
        ok_v = self._shader.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex,   vert_src)
        ok_f = self._shader.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, frag_src)
        linked = self._shader.link()
        if not (ok_v and ok_f and linked):
            import logging
            logging.getLogger("ImproveImgSLI").error(
                "CaptureRingPass: shader compile/link failed: %s", self._shader.log()
            )
            self._shader = None

    def should_paint(self, ctx) -> bool:
        if is_single_image_preview_scene(ctx):
            return False
        return bool(self._resolve_capture_circles(ctx.widget, ctx))

    def paint(self, widget, ctx) -> None:
        if not self._shader or not self._shader.programId():
            return
        w, h = ctx.width, ctx.height
        if w <= 0 or h <= 0:
            return

        capture_circles = self._resolve_capture_circles(widget, ctx)
        if not capture_circles:
            return

        scissor_enabled = begin_content_scissor(
            widget,
            force=bool(getattr(widget.runtime_state, "_clip_overlays_to_content_rect", False)),
        )
        pid = self._shader.programId()
        self._shader.bind()
        widget.vao.bind()

        gl.glUniform2f(gl.glGetUniformLocation(pid, "resolution"), float(w), float(h))

        for center, radius, color in capture_circles:
            if center is None or float(radius or 0.0) <= 0.0:
                continue
            draw_color = QColor(color)
            draw_color.setAlpha(255)
            cx, cy = widget_px_to_screen_px(widget, center.x(), center.y())
            gl.glUniform4f(
                gl.glGetUniformLocation(pid, "color"),
                draw_color.redF(), draw_color.greenF(),
                draw_color.blueF(), draw_color.alphaF(),
            )
            gl.glUniform2f(gl.glGetUniformLocation(pid, "center_px"), float(cx), float(cy))
            gl.glUniform1f(gl.glGetUniformLocation(pid, "radius_px"), float(radius) * float(ctx.zoom_level))
            gl.glUniform1f(
                gl.glGetUniformLocation(pid, "lineWidth_px"),
                float(ctx.resolved_style.annotation_ring_stroke_px),
            )
            gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)

        widget.vao.release()
        self._shader.release()
        end_content_scissor(widget, scissor_enabled)

    def cleanup(self, widget) -> None:
        self._shader = None

GL_RENDER_PASSES: list[CanvasGLRenderPass] = [CaptureRingPass()]
