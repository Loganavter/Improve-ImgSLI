from __future__ import annotations

from OpenGL import GL as gl
from PySide6.QtGui import QColor
from PySide6.QtOpenGL import QOpenGLShader, QOpenGLShaderProgram

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
    visibility = SceneVisibility.ALL

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
        state = getattr(ctx.widget, "runtime_state", None) if hasattr(ctx, "widget") else None
        return bool(
            not is_single_image_preview_scene(ctx)
            and state is not None
            and getattr(state, "_guide_sets", ())
            and ctx.width > 0
            and ctx.height > 0
        )

    def paint(self, widget, ctx) -> None:
        if not self._shader or not self._shader.programId():
            return
        guide_sets = tuple(getattr(widget.runtime_state, "_guide_sets", ()))
        if not guide_sets:
            return

        scissor_enabled = begin_content_scissor(
            widget,
            force=bool(getattr(widget.runtime_state, "_clip_overlays_to_content_rect", False)),
        )
        pid = self._shader.programId()
        self._shader.bind()
        widget.vao.bind()

        gl.glUniform2f(
            gl.glGetUniformLocation(pid, "resolution"),
            float(ctx.width), float(ctx.height),
        )

        for capture_center, capture_radius, target_centers, target_radii, color in guide_sets:
            if capture_center is None:
                continue
            end_px = widget_px_to_screen_px(widget, capture_center.x(), capture_center.y())
            end_radius_px = max(0.0, float(capture_radius or 0.0) * float(ctx.zoom_level))
            draw_color = QColor(color)
            for index, target_center in enumerate(tuple(target_centers or ())):
                if target_center is None:
                    continue
                target_radius = (
                    target_radii[index]
                    if index < len(target_radii)
                    else (target_radii[-1] if target_radii else 0.0)
                )
                start_px = widget_px_to_screen_px(widget, target_center.x(), target_center.y())
                gl.glUniform4f(
                    gl.glGetUniformLocation(pid, "color"),
                    draw_color.redF(), draw_color.greenF(),
                    draw_color.blueF(), draw_color.alphaF(),
                )
                gl.glUniform1f(gl.glGetUniformLocation(pid, "endRadius_px"), end_radius_px)
                gl.glUniform1f(
                    gl.glGetUniformLocation(pid, "lineWidth_px"),
                    float(ctx.resolved_style.annotation_line_stroke_px),
                )
                gl.glUniform1f(
                    gl.glGetUniformLocation(pid, "startRadius_px"),
                    max(0.0, float(target_radius or 0.0) * float(ctx.zoom_level)),
                )
                gl.glUniform2f(gl.glGetUniformLocation(pid, "start_px"), float(start_px[0]), float(start_px[1]))
                gl.glUniform2f(gl.glGetUniformLocation(pid, "end_px"), float(end_px[0]), float(end_px[1]))
                gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)

        widget.vao.release()
        self._shader.release()
        end_content_scissor(widget, scissor_enabled)

    def cleanup(self, widget) -> None:
        self._shader = None

GL_RENDER_PASSES: list[CanvasGLRenderPass] = [GuidesPass()]
