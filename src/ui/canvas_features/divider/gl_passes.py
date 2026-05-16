from __future__ import annotations

from OpenGL import GL as gl
from PyQt6.QtGui import QColor
from PyQt6.QtOpenGL import QOpenGLShader, QOpenGLShaderProgram

from ui.canvas_infra.scene.gl_pass_contract import CanvasGLRenderPass
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole

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
    float aa = 1.15;
    float alpha = 1.0 - smoothstep(max(0.0, halfThicknessPx - aa), halfThicknessPx + aa, dist);
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

class DividerPass(CanvasGLRenderPass):
    stack_role = CanvasStackRole.UNDERLAY_SPLIT

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
        return getattr(ctx.render_list, "divider", None) is not None

    def paint(self, widget, ctx) -> None:
        if not self._shader or not self._shader.programId():
            return
        divider = getattr(ctx.render_list, "divider", None)
        if divider is None:
            return

        scissor_enabled = _begin_screen_scissor(widget, divider.clip_rect_px)
        pid = self._shader.programId()
        self._shader.bind()
        widget.vao.bind()
        gl.glUniform2f(gl.glGetUniformLocation(pid, "resolution"), float(ctx.width), float(ctx.height))
        gl.glUniform1f(gl.glGetUniformLocation(pid, "positionPx"), float(divider.position_px))
        gl.glUniform1f(gl.glGetUniformLocation(pid, "halfThicknessPx"), float(divider.thickness_px) * 0.5)
        gl.glUniform1i(gl.glGetUniformLocation(pid, "isHorizontal"), 1 if divider.is_horizontal else 0)
        color = QColor(divider.color)
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
