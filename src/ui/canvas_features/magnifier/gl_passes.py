from __future__ import annotations

from dataclasses import dataclass

from OpenGL import GL as gl
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtOpenGL import QOpenGLShader, QOpenGLShaderProgram

from ui.canvas_infra.scene.gl_pass_contract import CanvasGLRenderPass
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole
from ui.widgets.gl_canvas.render_common import (
    draw_qimage_overlay_texture,
    new_overlay_image,
    widget_px_to_screen_px,
)
from ui.widgets.gl_canvas.render_config import begin_content_scissor, end_content_scissor

import logging
_log = logging.getLogger("ImproveImgSLI")

def _prolog(is_gles: bool, *, fragment: bool = False) -> str:
    if not is_gles:
        return "#version 330 core"
    lines = ["#version 300 es", "precision highp float;", "precision highp int;"]
    if fragment:
        lines.append("precision mediump sampler2D;")
    return "\n".join(lines)

def _compile(widget, vert_src: str, frag_src: str, label: str) -> QOpenGLShaderProgram | None:
    prog = QOpenGLShaderProgram()
    ok_v = prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex,   vert_src)
    ok_f = prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, frag_src)
    linked = prog.link()
    if not (ok_v and ok_f and linked):
        _log.error("%s: shader compile/link failed: %s", label, prog.log())
        return None
    return prog

_ARC_VERT = """
layout(location = 0) in vec2 aPos;
layout(location = 1) in vec2 aTexCoord;
out vec2 TexCoord;
void main() {
    gl_Position = vec4(aPos, 0.0, 1.0);
    TexCoord = aTexCoord;
}
"""

_ARC_FRAG = """
in vec2 TexCoord;
out vec4 FragColor;
uniform vec2 resolution;
uniform vec2 center_px;
uniform float radius_px;
uniform float lineWidth_px;
uniform vec4 color;
uniform float startAngleDeg;
uniform float spanAngleDeg;
void main() {
    vec2 frag_px = TexCoord * resolution;
    float dist   = distance(frag_px, center_px);
    float half_w = max(0.5, lineWidth_px * 0.5);
    float aa     = 1.15;
    float delta  = abs(dist - radius_px);
    float solid_w = max(0.0, half_w - aa);
    float ring   = 1.0 - smoothstep(solid_w, half_w + aa, delta);
    if (ring <= 0.01) discard;
    float angle_deg = degrees(atan(-(frag_px.y - center_px.y), frag_px.x - center_px.x));
    if (angle_deg < 0.0) angle_deg += 360.0;
    bool in_arc;
    if (abs(spanAngleDeg) >= 359.9) {
        in_arc = true;
    } else {
        float sa = mod(startAngleDeg, 360.0);
        if (sa < 0.0) sa += 360.0;
        float ea = mod(startAngleDeg + spanAngleDeg, 360.0);
        if (ea < 0.0) ea += 360.0;
        if (sa <= ea) {
            in_arc = (angle_deg >= sa && angle_deg <= ea);
        } else {
            in_arc = (angle_deg >= sa || angle_deg <= ea);
        }
    }
    if (!in_arc) discard;
    // dashed line: compute arc-length from start of arc, then stripe
    float sa2 = mod(startAngleDeg, 360.0);
    if (sa2 < 0.0) sa2 += 360.0;
    float angle_from_start = mod(angle_deg - sa2 + 360.0, 360.0);
    float arc_len_px = angle_from_start * 3.14159265 / 180.0 * radius_px;
    float dash_cycle = 12.0;
    if (mod(arc_len_px, dash_cycle) > 8.0) discard;
    FragColor = vec4(color.rgb, color.a * ring);
}
"""

class OccludedArcPass(CanvasGLRenderPass):
    """Draws the occluded arc segments of the capture ring when dragging."""

    stack_role = CanvasStackRole.ANNOTATION_BORDER

    def initialize(self, widget) -> None:
        is_gles = bool(widget.context().isOpenGLES())
        self._shader = _compile(
            widget,
            f"{_prolog(is_gles)}\n{_ARC_VERT}",
            f"{_prolog(is_gles, fragment=True)}\n{_ARC_FRAG}",
            "OccludedArcPass",
        )

    def should_paint(self, ctx) -> bool:
        magnifier = getattr(ctx.render_list, "magnifier", None)
        return bool(getattr(magnifier, "occluded_capture_arcs", None))

    def paint(self, widget, ctx) -> None:
        if not self._shader or not self._shader.programId():
            return
        w, h = ctx.width, ctx.height
        magnifier = getattr(ctx.render_list, "magnifier", None)
        arcs = list(getattr(magnifier, "occluded_capture_arcs", []) or [])
        if not (arcs and w > 0 and h > 0):
            return

        scissor_enabled = begin_content_scissor(
            widget,
            force=bool(getattr(magnifier, "clip_to_content", False)),
        )
        pid = self._shader.programId()
        self._shader.bind()
        widget.vao.bind()

        gl.glUniform2f(gl.glGetUniformLocation(pid, "resolution"), float(w), float(h))

        for arc in arcs:
            if len(arc) < 5:
                continue
            center, radius, start_deg, span_deg, is_active = arc
            if radius <= 0 or span_deg <= 0.25:
                continue
            base_color = QColor(255, 105, 170, 255 if is_active else 210)
            cx, cy = widget_px_to_screen_px(widget, center.x(), center.y())
            scaled_radius  = float(radius) * ctx.zoom_level
            line_width_px = max(1.0, float(ctx.resolved_style.occluded_arc_stroke_px))
            gl.glUniform4f(
                gl.glGetUniformLocation(pid, "color"),
                base_color.redF(), base_color.greenF(),
                base_color.blueF(), base_color.alphaF(),
            )
            gl.glUniform2f(gl.glGetUniformLocation(pid, "center_px"),    float(cx), float(cy))
            gl.glUniform1f(gl.glGetUniformLocation(pid, "radius_px"),    float(scaled_radius))
            gl.glUniform1f(gl.glGetUniformLocation(pid, "lineWidth_px"), float(line_width_px))
            gl.glUniform1f(gl.glGetUniformLocation(pid, "startAngleDeg"), float(start_deg))
            gl.glUniform1f(gl.glGetUniformLocation(pid, "spanAngleDeg"),  float(span_deg))
            gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)

        widget.vao.release()
        self._shader.release()
        end_content_scissor(widget, scissor_enabled)

    def cleanup(self, widget) -> None:
        self._shader = None

_MAG_VERT = """
layout(location = 0) in vec2 aPos;
layout(location = 1) in vec2 aTexCoord;
uniform vec4 quadBounds;
uniform float magZoom;
uniform vec2 magPan;
out vec2 TexCoord;
void main() {
    float x = mix(quadBounds.x, quadBounds.z, aTexCoord.x);
    float y = mix(quadBounds.y, quadBounds.w, 1.0 - aTexCoord.y);
    x = x * magZoom + magPan.x * magZoom * 2.0;
    y = y * magZoom - magPan.y * magZoom * 2.0;
    gl_Position = vec4(x, y, 0.0, 1.0);
    TexCoord = aTexCoord;
}
"""

_MAG_FRAG = """
in vec2 TexCoord;
out vec4 FragColor;

uniform sampler2D magTex;
uniform sampler2D magTex2;
uniform sampler2D circleMaskTex;

uniform float radius_px;
uniform float borderWidth;
uniform vec4  borderColor;
uniform bool  useCircleMask;

uniform float internalSplit;
uniform bool  combHorizontal;
uniform bool  showCombDivider;
uniform vec4  combDividerColor;
uniform float combDividerThickness;

uniform sampler2D bgTex1;
uniform sampler2D bgTex2;
uniform sampler2D bgTexDiff;
uniform vec4  uvRect1;
uniform vec4  uvRect2;
uniform float diffThreshold;

vec4 applyChannel(vec4 c) {
#if MAG_CHANNEL_MODE == 1
    return vec4(c.r, 0.0, 0.0, c.a);
#elif MAG_CHANNEL_MODE == 2
    return vec4(0.0, c.g, 0.0, c.a);
#elif MAG_CHANNEL_MODE == 3
    return vec4(0.0, 0.0, c.b, c.a);
#elif MAG_CHANNEL_MODE == 4
    float l = dot(c.rgb, vec3(0.299, 0.587, 0.114));
    return vec4(l, l, l, c.a);
#else
    return c;
#endif
}

float luminance(vec3 c) { return dot(c, vec3(0.299, 0.587, 0.114)); }

vec4 sampleNearest(sampler2D tex, vec2 uv) {
    ivec2 texSize = textureSize(tex, 0);
    vec2 texelPos = uv * vec2(texSize) - 0.5;
    ivec2 texel = ivec2(round(texelPos));
    texel = clamp(texel, ivec2(0), texSize - ivec2(1));
    return texelFetch(tex, texel, 0);
}

float cubicWeight(float x) {
    float ax = abs(x);
    if (ax <= 1.0) return (1.5*ax - 2.5)*ax*ax + 1.0;
    if (ax <= 2.0) return ((-0.5*ax + 2.5)*ax - 4.0)*ax + 2.0;
    return 0.0;
}

vec4 sampleBicubic(sampler2D tex, vec2 uv) {
    ivec2 texSizeI = textureSize(tex, 0);
    vec2 texSize = vec2(texSizeI);
    vec2 pos  = uv * texSize - 0.5;
    vec2 base = floor(pos);
    vec2 f    = fract(pos);
    vec4 result = vec4(0.0);
    float totalWeight = 0.0;
    for (int j = -1; j <= 2; j++) {
        float wy = cubicWeight(float(j) - f.y);
        for (int k = -1; k <= 2; k++) {
            float wx = cubicWeight(float(k) - f.x);
            float w  = wx * wy;
            ivec2 sampleTexel = clamp(ivec2(base) + ivec2(k, j), ivec2(0), texSizeI - ivec2(1));
            result += texelFetch(tex, sampleTexel, 0) * w;
            totalWeight += w;
        }
    }
    if (totalWeight <= 0.0) {
        ivec2 fb = clamp(ivec2(round(pos)), ivec2(0), texSizeI - ivec2(1));
        return texelFetch(tex, fb, 0);
    }
    return result / totalWeight;
}

float sinc(float x) {
    float ax = abs(x);
    if (ax < 1e-5) return 1.0;
    float pix = 3.14159265358979323846 * x;
    return sin(pix) / pix;
}

float lanczosWeight(float x, float a) {
    float ax = abs(x);
    if (ax >= a) return 0.0;
    return sinc(x) * sinc(x / a);
}

vec4 sampleLanczos(sampler2D tex, vec2 uv) {
    const float A = 3.0;
    ivec2 texSizeI = textureSize(tex, 0);
    vec2 texSize = vec2(texSizeI);
    vec2 pos  = uv * texSize - 0.5;
    ivec2 base = ivec2(floor(pos));
    vec2 f    = fract(pos);
    vec4 result = vec4(0.0);
    float totalWeight = 0.0;
    for (int j = -2; j <= 3; j++) {
        float wy = lanczosWeight(float(j) - f.y, A);
        for (int k = -2; k <= 3; k++) {
            float wx = lanczosWeight(float(k) - f.x, A);
            float w  = wx * wy;
            if (w == 0.0) continue;
            ivec2 st = clamp(base + ivec2(k, j), ivec2(0), texSizeI - ivec2(1));
            result += texelFetch(tex, st, 0) * w;
            totalWeight += w;
        }
    }
    if (totalWeight <= 0.0) {
        ivec2 fb = clamp(ivec2(round(pos)), ivec2(0), texSizeI - ivec2(1));
        return texelFetch(tex, fb, 0);
    }
    return result / totalWeight;
}

vec4 sampleEwaLanczos(sampler2D tex, vec2 uv) {
    const float A = 3.0;
    const int MAX_RADIUS = 6;
    ivec2 texSizeI = textureSize(tex, 0);
    vec2 texSize = vec2(texSizeI);
    vec2 pos = uv * texSize - 0.5;
    vec2 dx = dFdx(pos);
    vec2 dy = dFdy(pos);
    mat2 footprint = mat2(
        dot(dx, dx) + 1.0, dot(dx, dy),
        dot(dx, dy), dot(dy, dy) + 1.0
    );
    float det = footprint[0][0]*footprint[1][1] - footprint[0][1]*footprint[1][0];
    if (det <= 1e-6) { return sampleLanczos(tex, uv); }
    mat2 invF = mat2(
        footprint[1][1], -footprint[0][1],
        -footprint[1][0], footprint[0][0]
    ) / det;
    float boundX = min(float(MAX_RADIUS), ceil(A * sqrt(max(1.0, footprint[0][0]))));
    float boundY = min(float(MAX_RADIUS), ceil(A * sqrt(max(1.0, footprint[1][1]))));
    ivec2 center = ivec2(floor(pos));
    vec4 result = vec4(0.0);
    float totalWeight = 0.0;
    for (int j = -MAX_RADIUS; j <= MAX_RADIUS; j++) {
        if (abs(j) > int(boundY)) continue;
        for (int k = -MAX_RADIUS; k <= MAX_RADIUS; k++) {
            if (abs(k) > int(boundX)) continue;
            vec2 d = vec2(float(k), float(j)) - fract(pos);
            float r2 = dot(d, invF * d);
            if (r2 >= A * A) continue;
            float w = lanczosWeight(sqrt(r2), A);
            if (w == 0.0) continue;
            ivec2 st = clamp(center + ivec2(k, j), ivec2(0), texSizeI - ivec2(1));
            result += texelFetch(tex, st, 0) * w;
            totalWeight += w;
        }
    }
    if (totalWeight <= 0.0) { return sampleLanczos(tex, uv); }
    return result / totalWeight;
}

vec4 sampleInterp(sampler2D tex, vec2 uv) {
#if MAG_INTERP_MODE == 0
    return sampleNearest(tex, uv);
#elif MAG_INTERP_MODE == 2
    return sampleBicubic(tex, uv);
#elif MAG_INTERP_MODE == 3
    return sampleLanczos(tex, uv);
#elif MAG_INTERP_MODE == 4
    return sampleEwaLanczos(tex, uv);
#else
    return texture(tex, uv);
#endif
}

vec4 sampleBgFromSource(int source, vec2 tc) {
    vec2 uv; vec4 c;
    if (source == 0) {
        uv = mix(uvRect1.xy, uvRect1.zw, tc);
        c  = sampleInterp(bgTex1, uv);
    } else if (source == 1) {
        uv = mix(uvRect2.xy, uvRect2.zw, tc);
        c  = sampleInterp(bgTex2, uv);
    } else {
        uv = mix(uvRect1.xy, uvRect1.zw, tc);
        c  = sampleInterp(bgTexDiff, uv);
    }
    return applyChannel(c);
}

vec4 sampleSelectedBg(vec2 tc) {
#if MAG_SOURCE_MODE == 1
    return sampleBgFromSource(1, tc);
#elif MAG_SOURCE_MODE == 2
    return sampleBgFromSource(2, tc);
#else
    return sampleBgFromSource(0, tc);
#endif
}

vec4 computeDiff(vec2 tc) {
    vec2 uv1 = mix(uvRect1.xy, uvRect1.zw, tc);
    vec2 uv2 = mix(uvRect2.xy, uvRect2.zw, tc);
    vec4 c1  = sampleInterp(bgTex1, uv1);
    vec4 c2  = sampleInterp(bgTex2, uv2);
#if MAG_DIFF_MODE == 1
    vec3 diff = abs(c1.rgb - c2.rgb);
    float maxDiff = max(diff.r, max(diff.g, diff.b));
    if (maxDiff > diffThreshold) { return vec4(1.0, 0.35, 0.47, 1.0); }
    return applyChannel(c1);
#elif MAG_DIFF_MODE == 2
    vec3 diff = abs(c1.rgb - c2.rgb);
    float g = clamp(luminance(diff) * 4.0, 0.0, 1.0);
    return vec4(g, g, g, 1.0);
#elif MAG_DIFF_MODE == 3
    vec2 uv   = mix(uvRect1.xy, uvRect1.zw, tc);
    vec2 step = (uvRect1.zw - uvRect1.xy) / vec2(textureSize(bgTex1, 0));
    float tl = luminance(texture(bgTex1, uv + vec2(-step.x, -step.y)).rgb);
    float t  = luminance(texture(bgTex1, uv + vec2( 0.0,    -step.y)).rgb);
    float tr = luminance(texture(bgTex1, uv + vec2( step.x, -step.y)).rgb);
    float l  = luminance(texture(bgTex1, uv + vec2(-step.x,  0.0   )).rgb);
    float r  = luminance(texture(bgTex1, uv + vec2( step.x,  0.0   )).rgb);
    float bl = luminance(texture(bgTex1, uv + vec2(-step.x,  step.y)).rgb);
    float b  = luminance(texture(bgTex1, uv + vec2( 0.0,     step.y)).rgb);
    float br = luminance(texture(bgTex1, uv + vec2( step.x,  step.y)).rgb);
    float gx = -tl - 2.0*l - bl + tr + 2.0*r + br;
    float gy = -tl - 2.0*t - tr + bl + 2.0*b + br;
    float edge = smoothstep(0.05, 0.3, sqrt(gx*gx + gy*gy));
    return vec4(edge, edge, edge, 1.0);
#elif MAG_DIFF_MODE == 4
    vec2 uv = mix(uvRect1.xy, uvRect1.zw, tc);
    return applyChannel(sampleInterp(bgTexDiff, uv));
#else
    return applyChannel(c1);
#endif
}

void main() {
    vec4 col;
#ifdef MAG_GPU_SAMPLING
    #ifdef MAG_COMBINED
        float coord = combHorizontal ? TexCoord.y : TexCoord.x;
        col = (coord < internalSplit) ? sampleBgFromSource(0, TexCoord) : sampleBgFromSource(1, TexCoord);
        if (showCombDivider && combDividerThickness > 0.0) {
            float dist = abs(coord - internalSplit);
            if (dist < combDividerThickness) { col = mix(col, combDividerColor, combDividerColor.a); }
        }
    #elif MAG_SOURCE_MODE == 2 && MAG_DIFF_MODE != 0
        col = computeDiff(TexCoord);
    #else
        col = sampleSelectedBg(TexCoord);
    #endif
#else
    #ifdef MAG_COMBINED
        float coord = combHorizontal ? TexCoord.y : TexCoord.x;
        col = (coord < internalSplit) ? texture(magTex, TexCoord) : texture(magTex2, TexCoord);
        if (showCombDivider && combDividerThickness > 0.0) {
            float dist = abs(coord - internalSplit);
            if (dist < combDividerThickness) { col = mix(col, combDividerColor, combDividerColor.a); }
        }
    #else
        col = texture(magTex, TexCoord);
    #endif
#endif

    if (useCircleMask) {
        float outer_mask = texture(circleMaskTex, TexCoord).r;
        if (outer_mask <= 0.0) discard;
        if (borderWidth >= radius_px - 0.5) {
            FragColor = vec4(borderColor.rgb, outer_mask * borderColor.a);
            return;
        }
        if (borderWidth <= 0.0) {
            FragColor = vec4(col.rgb, col.a * outer_mask);
            return;
        }
        float inner_r = max(radius_px - borderWidth + 1.0, 0.0);
        float inner_mask = 0.0;
        if (inner_r > 0.0) {
            float inner_scale = radius_px / inner_r;
            vec2 inner_uv = (TexCoord - vec2(0.5)) * inner_scale + vec2(0.5);
            if (inner_uv.x >= 0.0 && inner_uv.x <= 1.0 && inner_uv.y >= 0.0 && inner_uv.y <= 1.0) {
                inner_mask = texture(circleMaskTex, inner_uv).r;
            }
        }
        float border_mask  = smoothstep(0.42, 0.92, outer_mask);
        float border_alpha = border_mask * borderColor.a;
        float fill_alpha   = col.a * inner_mask;
        float out_alpha    = fill_alpha + border_alpha * (1.0 - fill_alpha);
        if (out_alpha <= 0.001) discard;
        col.rgb = (col.rgb * fill_alpha + borderColor.rgb * border_alpha * (1.0 - fill_alpha)) / out_alpha;
        col.a   = out_alpha;
    }
    FragColor = col;
}
"""

@dataclass(frozen=True, slots=True)
class _MagShaderKey:
    gpu_sampling: bool
    combined: bool
    interp_mode: int = 1
    diff_mode:   int = 0
    channel_mode: int = 0
    source_mode:  int = 0

def _norm(mode: int, valid: tuple[int, ...], default: int) -> int:
    return mode if mode in valid else default

def _build_mag_frag(key: _MagShaderKey, *, is_gles: bool) -> str:
    gpu_sampling = bool(key.gpu_sampling)
    combined     = bool(key.combined)
    interp  = _norm(key.interp_mode if gpu_sampling else 1,         (0,1,2,3,4), 1)
    channel = _norm(key.channel_mode,                                (0,1,2,3,4), 0)
    source  = _norm(key.source_mode if gpu_sampling and not combined else 0, (0,1,2), 0)
    diff    = _norm(key.diff_mode if gpu_sampling and not combined and source == 2 else 0,
                    (0,1,2,3,4), 0)

    if is_gles:
        header = [
            "#version 300 es",
            "#ifdef GL_OES_standard_derivatives",
            "#extension GL_OES_standard_derivatives : enable",
            "#endif",
            "precision highp float;",
            "precision highp int;",
            "precision mediump sampler2D;",
        ]
    else:
        header = [
            "#version 330 core",
            "#ifdef GL_OES_standard_derivatives",
            "#extension GL_OES_standard_derivatives : enable",
            "#endif",
        ]
    if gpu_sampling: header.append("#define MAG_GPU_SAMPLING 1")
    if combined:     header.append("#define MAG_COMBINED 1")
    header.append(f"#define MAG_INTERP_MODE {interp}")
    header.append(f"#define MAG_DIFF_MODE {diff}")
    header.append(f"#define MAG_CHANNEL_MODE {channel}")
    header.append(f"#define MAG_SOURCE_MODE {source}")
    header.append(_MAG_FRAG)
    return "\n".join(header)

class MagnifierPass(CanvasGLRenderPass):
    """Renders all magnifier circles using GPU sampling or pre-rendered textures."""

    stack_role = CanvasStackRole.IMAGE_OVERLAY_CONTENT

    def __init__(self) -> None:
        self._shader_cache: dict[_MagShaderKey, QOpenGLShaderProgram] = {}
        self._is_gles: bool = False

    def initialize(self, widget) -> None:
        self._is_gles = bool(widget.context().isOpenGLES())
        self._shader_cache = {}

    def _draw_slot_frame(
        self,
        widget,
        ctx,
        *,
        center_x: float,
        center_y: float,
        radius: float,
        border_color: QColor,
    ) -> None:
        overlay = new_overlay_image(ctx.width, ctx.height)
        painter = QPainter(overlay)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            draw_color = QColor(border_color)
            draw_color.setAlpha(255)
            painter.setBrush(draw_color)
            cx, cy = widget_px_to_screen_px(widget, center_x, center_y)
            scaled_radius = float(radius) * float(ctx.zoom_level or 1.0)
            painter.drawEllipse(QPointF(cx, cy), scaled_radius, scaled_radius)
        finally:
            painter.end()
        draw_qimage_overlay_texture(widget, overlay)

    def _get_shader(self, widget, key: _MagShaderKey) -> QOpenGLShaderProgram | None:
        prog = self._shader_cache.get(key)
        if prog is not None and prog.isLinked():
            return prog
        prog = _compile(
            widget,
            f"{_prolog(self._is_gles)}\n{_MAG_VERT}",
            _build_mag_frag(key, is_gles=self._is_gles),
            f"MagnifierPass[{key}]",
        )
        if prog is not None:
            self._shader_cache[key] = prog
        return prog

    def _build_key(self, ctx, gpu_slot, combined: bool) -> _MagShaderKey:
        magnifier = getattr(ctx.render_list, "magnifier", None)
        if gpu_slot:
            source_mode = int(gpu_slot.get("source", 0) or 0)
            diff_mode = (
                int(getattr(magnifier, "gpu_diff_mode", 0) or 0)
                if source_mode == 2 and not combined
                else 0
            )
            return _MagShaderKey(
                gpu_sampling=True,
                combined=combined,
                interp_mode=int(getattr(magnifier, "gpu_interp_mode", 1))
                if getattr(magnifier, "gpu_interp_mode", None) is not None
                else 1,
                diff_mode=diff_mode,
                channel_mode=int(getattr(magnifier, "gpu_channel_mode", 0) or 0),
                source_mode=source_mode if not combined else 0,
            )
        return _MagShaderKey(gpu_sampling=False, combined=combined)

    def should_paint(self, ctx) -> bool:
        magnifier = getattr(ctx.render_list, "magnifier", None)
        if magnifier is None or not bool(getattr(magnifier, "render_enabled", False)):
            return False
        return bool(getattr(magnifier, "quads", ()))

    def paint(self, widget, ctx) -> None:
        try:
            self._paint_inner(widget, ctx)
        except Exception:
            _log.exception("MagnifierPass paint failed")
            self._shader_cache.clear()

    def _paint_inner(self, widget, ctx) -> None:
        w, h = ctx.width, ctx.height
        if not (w > 0 and h > 0):
            return

        magnifier = getattr(ctx.render_list, "magnifier", None)
        if magnifier is None:
            return

        is_gpu = bool(magnifier.gpu_active)
        use_source_textures = bool(
            is_gpu
            and ctx.shader_letterbox_mode
            and ctx.source_images_ready
            and ctx.source_texture_ids[0]
            and ctx.source_texture_ids[1]
        )
        bg_filter = gl.GL_LINEAR if magnifier.gpu_interp_mode == 1 else gl.GL_NEAREST
        zoom  = ctx.zoom_level
        pan_x = ctx.pan_offset_x
        pan_y = ctx.pan_offset_y

        for i, quad in enumerate(magnifier.quads):
            if not quad:
                continue
            x0, y0, x1, y1, _cx_px, _cy_px, r_px = quad

            gpu_slot = (
                magnifier.gpu_slots[i]
                if is_gpu and i < len(magnifier.gpu_slots)
                else None
            )
            if not gpu_slot:
                tid = widget._mag_tex_ids[i] if i < len(widget._mag_tex_ids) else 0
                if not tid:
                    continue
            elif not use_source_textures:

                continue

            if gpu_slot:
                combined   = bool(gpu_slot.get("is_combined", False))
                comb_params = None
            else:
                comb_params = (
                    magnifier.combined_params[i]
                    if i < len(magnifier.combined_params)
                    else None
                )
                combined    = comb_params is not None

            shader = self._get_shader(widget, self._build_key(ctx, gpu_slot, combined))
            if shader is None:
                continue
            pid = shader.programId()

            slot_border_width = (
                float(gpu_slot.get("border_width", magnifier.border_width))
                if gpu_slot else float(magnifier.border_width)
            )
            border_width = max(0.0, slot_border_width)
            content_radius = max(1.0, r_px - border_width + 1.0)
            if border_width > 0.0:
                slot_border_color = (
                    gpu_slot.get("border_color", magnifier.border_color)
                    if gpu_slot else magnifier.border_color
                )
                self._draw_slot_frame(
                    widget,
                    ctx,
                    center_x=float(_cx_px),
                    center_y=float(_cy_px),
                    radius=float(r_px),
                    border_color=QColor(slot_border_color),
                )

            def _comb_divider_thickness_uv(params, fallback: float = 0.005) -> float:
                if not params:
                    return 0.0
                dpx = float(params.get("divider_thickness_px", 0.0) or 0.0)
                if dpx <= 0.0:
                    return float(params.get("divider_thickness_uv", 0.0) or 0.0)
                diam = max(1.0, content_radius * 2.0)
                return (dpx / diam) * 0.5 if diam > 0.0 else fallback

            content_x0 = ((_cx_px - content_radius) / w) * 2.0 - 1.0
            content_x1 = ((_cx_px + content_radius) / w) * 2.0 - 1.0
            content_y1 = 1.0 - (((_cy_px - content_radius) / h) * 2.0)
            content_y0 = 1.0 - (((_cy_px + content_radius) / h) * 2.0)

            shader.bind()
            shader.setUniformValue("quadBounds", content_x0, content_y0, content_x1, content_y1)
            shader.setUniformValue("magZoom", zoom)
            gl.glUniform2f(gl.glGetUniformLocation(pid, "magPan"), pan_x, pan_y)
            shader.setUniformValue("useCircleMask", True)
            gl.glActiveTexture(gl.GL_TEXTURE4)
            gl.glBindTexture(gl.GL_TEXTURE_2D, widget._circle_mask_tex_id)
            gl.glUniform1i(gl.glGetUniformLocation(pid, "circleMaskTex"), 4)
            gl.glUniform1f(gl.glGetUniformLocation(pid, "radius_px"),   content_radius)
            gl.glUniform1f(gl.glGetUniformLocation(pid, "borderWidth"), 0.0)
            gl.glUniform4f(gl.glGetUniformLocation(pid, "borderColor"),  0.0, 0.0, 0.0, 0.0)
            if gpu_slot:
                gl.glUniform1f(gl.glGetUniformLocation(pid, "diffThreshold"), magnifier.gpu_diff_threshold)
                uv1 = gpu_slot.get("uv_rect", (0, 0, 1, 1))
                uv2 = gpu_slot.get("uv_rect2", uv1)
                gl.glUniform4f(gl.glGetUniformLocation(pid, "uvRect1"), *uv1)
                gl.glUniform4f(gl.glGetUniformLocation(pid, "uvRect2"), *uv2)
                tex1 = ctx.source_texture_ids[0] if use_source_textures else ctx.texture_ids[0]
                tex2 = ctx.source_texture_ids[1] if use_source_textures else ctx.texture_ids[1]
                gl.glActiveTexture(gl.GL_TEXTURE2)
                widget._set_texture_filter(tex1, bg_filter)
                gl.glBindTexture(gl.GL_TEXTURE_2D, tex1)
                gl.glUniform1i(gl.glGetUniformLocation(pid, "bgTex1"), 2)
                gl.glActiveTexture(gl.GL_TEXTURE3)
                widget._set_texture_filter(tex2, bg_filter)
                gl.glBindTexture(gl.GL_TEXTURE_2D, tex2)
                gl.glUniform1i(gl.glGetUniformLocation(pid, "bgTex2"), 3)
                gl.glActiveTexture(gl.GL_TEXTURE5)
                if ctx.diff_source_ready and ctx.diff_source_texture_id:
                    widget._set_texture_filter(ctx.diff_source_texture_id, bg_filter)
                    gl.glBindTexture(gl.GL_TEXTURE_2D, ctx.diff_source_texture_id)
                else:
                    gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
                gl.glUniform1i(gl.glGetUniformLocation(pid, "bgTexDiff"), 5)
            else:
                gl.glActiveTexture(gl.GL_TEXTURE5)
                gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
                gl.glUniform1i(gl.glGetUniformLocation(pid, "bgTexDiff"), 5)
                gl.glActiveTexture(gl.GL_TEXTURE0)
                gl.glBindTexture(gl.GL_TEXTURE_2D, widget._mag_tex_ids[i])
                gl.glUniform1i(gl.glGetUniformLocation(pid, "magTex"), 0)
                if combined:
                    comb_tid = widget._mag_combined_tex_ids[i] if i < len(widget._mag_combined_tex_ids) else 0
                    gl.glActiveTexture(gl.GL_TEXTURE2)
                    gl.glBindTexture(gl.GL_TEXTURE_2D, comb_tid)
                    gl.glUniform1i(gl.glGetUniformLocation(pid, "magTex2"), 2)

            if gpu_slot and combined:
                gl.glUniform1f(gl.glGetUniformLocation(pid, "internalSplit"),      gpu_slot.get("internal_split", 0.5))
                gl.glUniform1i(gl.glGetUniformLocation(pid, "combHorizontal"),     int(gpu_slot.get("horizontal", False)))
                gl.glUniform1i(gl.glGetUniformLocation(pid, "showCombDivider"),    int(gpu_slot.get("divider_visible", True)))
                dc = gpu_slot.get("divider_color", (1.0, 1.0, 1.0, 0.9))
                gl.glUniform4f(gl.glGetUniformLocation(pid, "combDividerColor"),     *dc)
                gl.glUniform1f(gl.glGetUniformLocation(pid, "combDividerThickness"), _comb_divider_thickness_uv(gpu_slot))
            elif gpu_slot:
                gl.glUniform1f(gl.glGetUniformLocation(pid, "internalSplit"),      0.5)
                gl.glUniform1i(gl.glGetUniformLocation(pid, "combHorizontal"),     0)
                gl.glUniform1i(gl.glGetUniformLocation(pid, "showCombDivider"),    0)
                gl.glUniform4f(gl.glGetUniformLocation(pid, "combDividerColor"),   1.0, 1.0, 1.0, 0.9)
                gl.glUniform1f(gl.glGetUniformLocation(pid, "combDividerThickness"), 0.0)
            elif combined:
                gl.glUniform1f(gl.glGetUniformLocation(pid, "internalSplit"),      comb_params.get("split", 0.5))
                gl.glUniform1i(gl.glGetUniformLocation(pid, "combHorizontal"),     int(comb_params.get("horizontal", False)))
                gl.glUniform1i(gl.glGetUniformLocation(pid, "showCombDivider"),    int(comb_params.get("divider_visible", True)))
                dc = comb_params.get("divider_color", (1.0, 1.0, 1.0, 0.9))
                gl.glUniform4f(gl.glGetUniformLocation(pid, "combDividerColor"),     *dc)
                gl.glUniform1f(gl.glGetUniformLocation(pid, "combDividerThickness"), _comb_divider_thickness_uv(comb_params))
            else:
                gl.glUniform1f(gl.glGetUniformLocation(pid, "internalSplit"),      0.5)
                gl.glUniform1i(gl.glGetUniformLocation(pid, "combHorizontal"),     0)
                gl.glUniform1i(gl.glGetUniformLocation(pid, "showCombDivider"),    0)
                gl.glUniform4f(gl.glGetUniformLocation(pid, "combDividerColor"),     1.0, 1.0, 1.0, 0.9)
                gl.glUniform1f(gl.glGetUniformLocation(pid, "combDividerThickness"), 0.0)

            widget.vao.bind()
            gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)
            widget.vao.release()
            shader.release()

        if is_gpu:
            tex1 = ctx.source_texture_ids[0] if use_source_textures else ctx.texture_ids[0]
            tex2 = ctx.source_texture_ids[1] if use_source_textures else ctx.texture_ids[1]
            widget._set_texture_filter(tex1, gl.GL_LINEAR)
            widget._set_texture_filter(tex2, gl.GL_LINEAR)

    def cleanup(self, widget) -> None:
        self._shader_cache.clear()

class MagnifierBorderPass(CanvasGLRenderPass):
    """Draw magnifier frames separately from the magnified content."""

    stack_role = CanvasStackRole.IMAGE_OVERLAY_FRAME

    def initialize(self, widget) -> None:
        return None

    def should_paint(self, ctx) -> bool:
        magnifier = getattr(ctx.render_list, "magnifier", None)
        if magnifier is None or not bool(getattr(magnifier, "render_enabled", False)):
            return False
        return bool(getattr(magnifier, "quads", ()))

    def paint(self, widget, ctx) -> None:
        magnifier = getattr(ctx.render_list, "magnifier", None)
        if magnifier is None:
            return

        overlay = new_overlay_image(ctx.width, ctx.height)
        painter = QPainter(overlay)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            for i, quad in enumerate(magnifier.quads):
                if not quad:
                    continue
                gpu_slot = (
                    magnifier.gpu_slots[i]
                    if bool(magnifier.gpu_active) and i < len(magnifier.gpu_slots)
                    else None
                )
                border_color = (
                    gpu_slot.get("border_color", magnifier.border_color)
                    if gpu_slot else magnifier.border_color
                )
                border_width = (
                    float(gpu_slot.get("border_width", magnifier.border_width))
                    if gpu_slot else float(magnifier.border_width)
                )
                if border_width <= 0.0:
                    continue
                x0, y0, x1, y1, _cx_px, _cy_px, r_px = quad
                cx, cy = widget_px_to_screen_px(widget, _cx_px, _cy_px)
                draw_color = QColor(border_color)

                draw_color.setAlpha(255)
                painter.setBrush(draw_color)
                painter.drawEllipse(QPointF(cx, cy), float(r_px), float(r_px))
        finally:
            painter.end()

        draw_qimage_overlay_texture(widget, overlay)

    def cleanup(self, widget) -> None:
        return None

class HiddenSelectionPass(CanvasGLRenderPass):
    stack_role = CanvasStackRole.DEBUG_VIS

    def should_paint(self, ctx) -> bool:
        magnifier = getattr(ctx.render_list, "magnifier", None)
        hidden_capture_circles = list(getattr(magnifier, "hidden_capture_circles", []) or [])
        hidden_magnifier_circles = list(getattr(magnifier, "hidden_magnifier_circles", []) or [])
        return bool(hidden_capture_circles or hidden_magnifier_circles)

    def paint(self, widget, ctx) -> None:
        magnifier = getattr(ctx.render_list, "magnifier", None)
        hidden_capture_circles = list(getattr(magnifier, "hidden_capture_circles", []) or [])
        hidden_magnifier_circles = list(getattr(magnifier, "hidden_magnifier_circles", []) or [])
        if not hidden_capture_circles and not hidden_magnifier_circles:
            return

        overlay = new_overlay_image(ctx.width, ctx.height)
        painter = QPainter(overlay)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            def _draw_ring(center, radius, *, active: bool, capture: bool):
                if center is None or radius <= 0:
                    return
                cx, cy = widget_px_to_screen_px(widget, center.x(), center.y())
                scaled_radius = float(radius) * ctx.zoom_level
                if scaled_radius <= 0:
                    return
                color = QColor(255, 105, 170, 255 if active else 210) if capture else QColor(70, 190, 255, 255 if active else 210)
                pen = QPen(color, max(1.0, float(ctx.resolved_style.hidden_selection_stroke_px)))
                pen.setCosmetic(True)
                pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.drawEllipse(QPointF(cx, cy), scaled_radius, scaled_radius)

            for center, radius, is_active in hidden_capture_circles:
                _draw_ring(center, radius, active=bool(is_active), capture=True)
            for center, radius, is_active in hidden_magnifier_circles:
                _draw_ring(center, radius, active=bool(is_active), capture=False)
        finally:
            painter.end()

        draw_qimage_overlay_texture(widget, overlay)

GL_RENDER_PASSES: list[CanvasGLRenderPass] = [
    MagnifierPass(),
    OccludedArcPass(),
    HiddenSelectionPass(),
]
