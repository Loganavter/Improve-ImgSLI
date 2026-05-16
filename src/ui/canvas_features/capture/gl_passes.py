from __future__ import annotations

from OpenGL import GL as gl
from PyQt6.QtGui import QColor
from PyQt6.QtOpenGL import QOpenGLShader, QOpenGLShaderProgram

from ui.canvas_infra.scene.gl_pass_contract import CanvasGLRenderPass
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole
from ui.widgets.gl_canvas.render_config import begin_content_scissor, end_content_scissor

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
        return bool(getattr(ctx.render_list, "capture_rings", ()))

    def paint(self, widget, ctx) -> None:
        if not self._shader or not self._shader.programId():
            return
        w, h = ctx.width, ctx.height
        if w <= 0 or h <= 0:
            return

        capture_rings = tuple(getattr(ctx.render_list, "capture_rings", ()))
        if not capture_rings:
            return

        scissor_enabled = begin_content_scissor(widget, force=bool(capture_rings[0].clip_to_content))
        pid = self._shader.programId()
        self._shader.bind()
        widget.vao.bind()

        gl.glUniform2f(gl.glGetUniformLocation(pid, "resolution"), float(w), float(h))

        for item in capture_rings:
            draw_color = QColor(item.color)
            draw_color.setAlpha(255)
            gl.glUniform4f(
                gl.glGetUniformLocation(pid, "color"),
                draw_color.redF(), draw_color.greenF(),
                draw_color.blueF(), draw_color.alphaF(),
            )
            gl.glUniform2f(gl.glGetUniformLocation(pid, "center_px"), float(item.center_px[0]), float(item.center_px[1]))
            gl.glUniform1f(gl.glGetUniformLocation(pid, "radius_px"), float(item.radius_px))
            gl.glUniform1f(gl.glGetUniformLocation(pid, "lineWidth_px"), float(item.line_width_px))
            gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)

        widget.vao.release()
        self._shader.release()
        end_content_scissor(widget, scissor_enabled)

    def cleanup(self, widget) -> None:
        self._shader = None

GL_RENDER_PASSES: list[CanvasGLRenderPass] = [CaptureRingPass()]
