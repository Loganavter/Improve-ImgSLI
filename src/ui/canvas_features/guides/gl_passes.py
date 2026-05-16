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
uniform vec2 start_px;
uniform vec2 end_px;
uniform float startRadius_px;
uniform float endRadius_px;
uniform float lineWidth_px;
uniform vec4 color;
void main() {
    vec2 frag_px = TexCoord * resolution;
    vec2 segment = end_px - start_px;
    float segment_len = length(segment);
    if (segment_len <= 0.0001) { discard; }
    vec2 dir = segment / segment_len;
    float source_overlap = max(lineWidth_px * 2.0, startRadius_px * 0.08);
    float start_cut = max(0.0, startRadius_px - source_overlap);
    float end_cut   = max(0.0, endRadius_px);
    float drawable_len = segment_len - start_cut - end_cut;
    if (drawable_len <= 0.0001) { discard; }
    vec2 clipped_start   = start_px + dir * start_cut;
    vec2 clipped_end     = end_px   - dir * end_cut;
    vec2 clipped_segment = clipped_end - clipped_start;
    float clipped_len_sq = dot(clipped_segment, clipped_segment);
    if (clipped_len_sq <= 0.0001) { discard; }
    float t = dot(frag_px - clipped_start, clipped_segment) / clipped_len_sq;
    if (t < 0.0 || t > 1.0) { discard; }
    vec2  closest = clipped_start + clipped_segment * t;
    float dist    = distance(frag_px, closest);
    float half_w  = max(0.5, lineWidth_px * 0.5);
    float aa      = 1.15;
    float alpha   = 1.0 - smoothstep(max(0.0, half_w - aa), half_w + aa, dist);
    if (alpha <= 0.01) discard;
    FragColor = vec4(color.rgb, color.a * alpha);
}
"""

def _prolog(is_gles: bool, *, fragment: bool = False) -> str:
    if not is_gles:
        return "#version 330 core"
    lines = ["#version 300 es", "precision highp float;", "precision highp int;"]
    if fragment:
        lines.append("precision mediump sampler2D;")
    return "\n".join(lines)

class GuidesPass(CanvasGLRenderPass):
    """Draws laser guide lines from capture center to each magnifier circle."""

    stack_role = CanvasStackRole.ANNOTATION_GUIDE

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
                "GuidesPass: shader compile/link failed: %s", self._shader.log()
            )
            self._shader = None

    def should_paint(self, ctx) -> bool:
        return bool(
            getattr(ctx.render_list, "guide_lines", ())
            and ctx.width > 0
            and ctx.height > 0
        )

    def paint(self, widget, ctx) -> None:
        if not self._shader or not self._shader.programId():
            return
        guide_lines = tuple(getattr(ctx.render_list, "guide_lines", ()))
        if not guide_lines:
            return

        scissor_enabled = begin_content_scissor(widget, force=bool(guide_lines[0].clip_to_content))
        pid = self._shader.programId()
        self._shader.bind()
        widget.vao.bind()

        gl.glUniform2f(
            gl.glGetUniformLocation(pid, "resolution"),
            float(ctx.width), float(ctx.height),
        )

        for line in guide_lines:
            gl.glUniform4f(
                gl.glGetUniformLocation(pid, "color"),
                line.color.redF(), line.color.greenF(),
                line.color.blueF(), line.color.alphaF(),
            )
            gl.glUniform1f(gl.glGetUniformLocation(pid, "endRadius_px"), float(line.end_radius_px))
            gl.glUniform1f(gl.glGetUniformLocation(pid, "lineWidth_px"), float(line.line_width_px))
            gl.glUniform1f(gl.glGetUniformLocation(pid, "startRadius_px"), float(line.start_radius_px))
            gl.glUniform2f(gl.glGetUniformLocation(pid, "start_px"), float(line.start_px[0]), float(line.start_px[1]))
            gl.glUniform2f(gl.glGetUniformLocation(pid, "end_px"), float(line.end_px[0]), float(line.end_px[1]))
            gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)

        widget.vao.release()
        self._shader.release()
        end_content_scissor(widget, scissor_enabled)

    def cleanup(self, widget) -> None:
        self._shader = None

GL_RENDER_PASSES: list[CanvasGLRenderPass] = [GuidesPass()]
