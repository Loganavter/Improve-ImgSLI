from __future__ import annotations

from dataclasses import dataclass

from OpenGL import GL as gl
from PyQt6.QtGui import QColor
from PyQt6.QtOpenGL import QOpenGLShader, QOpenGLShaderProgram

from ui.canvas_infra.scene.gl_pass_contract import (
    CanvasGLRenderPass,
    SceneVisibility,
    is_single_image_preview_scene,
)
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole
from ui.widgets.gl_canvas.render_common import (
    widget_px_to_screen_px,
)
from ui.widgets.gl_canvas.render_config import begin_content_scissor, end_content_scissor

import logging
_log = logging.getLogger("ImproveImgSLI")

def _ensure_qcolor(c) -> QColor:
    if isinstance(c, QColor):
        return c
    r = int(getattr(c, "r", 255) if hasattr(c, "r") else getattr(c, "red", lambda: 255)())
    g = int(getattr(c, "g", 255) if hasattr(c, "g") else getattr(c, "green", lambda: 255)())
    b = int(getattr(c, "b", 255) if hasattr(c, "b") else getattr(c, "blue", lambda: 255)())
    a = int(getattr(c, "a", 255) if hasattr(c, "a") else getattr(c, "alpha", lambda: 255)())
    return QColor(r, g, b, a)

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
    visibility = SceneVisibility.INTERACTIVE

    @staticmethod
    def _resolve_occluded_capture_arcs(ctx) -> tuple[object, ...]:
        payloads = (
            ctx.scene_frame.feature_payloads
            if isinstance(getattr(ctx.scene_frame, "feature_payloads", None), dict)
            else {}
        )
        arcs = payloads.get("occluded_capture_arcs")
        if arcs:
            return tuple(arcs)
        overlay = getattr(ctx, "feature_overlay", None)
        return tuple(getattr(overlay, "occluded_capture_arcs", ()) or ())

    def initialize(self, widget) -> None:
        is_gles = bool(widget.context().isOpenGLES())
        self._shader = _compile(
            widget,
            f"{_prolog(is_gles)}\n{_ARC_VERT}",
            f"{_prolog(is_gles, fragment=True)}\n{_ARC_FRAG}",
            "OccludedArcPass",
        )

    def should_paint(self, ctx) -> bool:
        if is_single_image_preview_scene(ctx):
            return False
        return bool(self._resolve_occluded_capture_arcs(ctx))

    def paint(self, widget, ctx) -> None:
        if not self._shader or not self._shader.programId():
            return
        w, h = ctx.width, ctx.height
        overlay = getattr(ctx, "feature_overlay", None)
        arcs = list(self._resolve_occluded_capture_arcs(ctx))
        if not (arcs and w > 0 and h > 0):
            return

        scissor_enabled = begin_content_scissor(
            widget,
            force=bool(getattr(overlay, "clip_to_content", False)),
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
            line_width_px = max(1.0, float(ctx.resolved_style.annotation_arc_stroke_px))
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
        vec2 circle_delta = TexCoord - vec2(0.5);
        float circle_dist_px = length(circle_delta) * (radius_px * 2.0);
        float aa = 1.15;
        float circle_alpha = 1.0 - smoothstep(
            max(0.0, radius_px - aa),
            radius_px + aa,
            circle_dist_px
        );
        if (circle_alpha <= 0.01) discard;
        if (borderWidth >= radius_px - 0.5) {
            FragColor = vec4(borderColor.rgb, borderColor.a * circle_alpha);
            return;
        }
        if (borderWidth <= 0.0) {
            FragColor = vec4(col.rgb, col.a * circle_alpha);
            return;
        }
        float inner_radius = max(0.0, radius_px - borderWidth);
        float content_alpha = 1.0 - smoothstep(
            max(0.0, inner_radius - aa),
            inner_radius + aa,
            circle_dist_px
        );
        float border_alpha = max(0.0, circle_alpha - content_alpha);
        vec3 rgb = (col.rgb * content_alpha) + (borderColor.rgb * border_alpha);
        float alpha = (col.a * content_alpha) + (borderColor.a * border_alpha);
        FragColor = vec4(rgb, alpha);
        return;
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
    visibility = SceneVisibility.ALL

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
        border_width: float,
        border_color: QColor,
    ) -> None:
        shader = self._get_disk_shader(widget)
        if not shader or not shader.programId():
            return
        cx, cy = widget_px_to_screen_px(widget, center_x, center_y)
        scaled_radius = float(radius) * float(ctx.zoom_level or 1.0)
        draw_color = _ensure_qcolor(border_color)

        pid = shader.programId()
        shader.bind()
        widget.vao.bind()
        gl.glUniform2f(gl.glGetUniformLocation(pid, "resolution"), float(ctx.width), float(ctx.height))
        gl.glUniform2f(gl.glGetUniformLocation(pid, "center_px"), float(cx), float(cy))
        gl.glUniform1f(gl.glGetUniformLocation(pid, "radius_px"), float(scaled_radius))
        gl.glUniform1f(
            gl.glGetUniformLocation(pid, "borderWidth_px"),
            float(border_width) * float(ctx.zoom_level or 1.0),
        )
        gl.glUniform4f(
            gl.glGetUniformLocation(pid, "color"),
            draw_color.redF(), draw_color.greenF(),
            draw_color.blueF(), 1.0,
        )
        gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)
        widget.vao.release()
        shader.release()

    def _get_disk_shader(self, widget) -> QOpenGLShaderProgram | None:
        key = "_disk_shader"
        prog = self._shader_cache.get(key)
        if prog is not None and prog.isLinked():
            return prog
        vert_src = f"{_prolog(self._is_gles)}\n{_ARC_VERT}"
        frag_src = f"{_prolog(self._is_gles, fragment=True)}\n{_BORDER_DISK_FRAG}"
        prog = _compile(widget, vert_src, frag_src, "MagnifierSlotFrame")
        if prog is not None:
            self._shader_cache[key] = prog
        return prog

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
        overlay = getattr(ctx, "feature_overlay", None)
        if gpu_slot:
            source_mode = int(gpu_slot.get("source", 0) or 0)
            diff_mode = (
                int(getattr(overlay, "gpu_diff_mode", 0) or 0)
                if source_mode == 2 and not combined
                else 0
            )
            return _MagShaderKey(
                gpu_sampling=True,
                combined=combined,
                interp_mode=int(getattr(overlay, "gpu_interp_mode", 1))
                if getattr(overlay, "gpu_interp_mode", None) is not None
                else 1,
                diff_mode=diff_mode,
                channel_mode=int(getattr(overlay, "gpu_channel_mode", 0) or 0),
                source_mode=source_mode if not combined else 0,
            )
        return _MagShaderKey(gpu_sampling=False, combined=combined)

    def should_paint(self, ctx) -> bool:
        if is_single_image_preview_scene(ctx):
            return False
        overlay = getattr(ctx, "feature_overlay", None)
        if overlay is None or not bool(getattr(overlay, "render_enabled", False)):
            return False
        return bool(getattr(overlay, "quads", ()))

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

        overlay = getattr(ctx, "feature_overlay", None)
        if overlay is None:
            return

        scissor_enabled = begin_content_scissor(
            widget,
            force=bool(getattr(overlay, "clip_to_content", False)),
        )

        is_gpu = bool(overlay.gpu_active)
        content_rect_px = getattr(ctx.scene_frame, "content_rect_px", None)
        image_rect_px = getattr(ctx.scene_frame, "image_rect_px", None)
        has_virtual_canvas_padding = (
            content_rect_px is not None
            and image_rect_px is not None
            and tuple(content_rect_px) != tuple(image_rect_px)
        )
        use_source_textures = bool(
            is_gpu
            and ctx.shader_letterbox_mode
            and ctx.source_images_ready
            and ctx.source_texture_ids[0]
            and ctx.source_texture_ids[1]
        )
        bg_filter = gl.GL_LINEAR if overlay.gpu_interp_mode == 1 else gl.GL_NEAREST
        zoom  = ctx.zoom_level
        pan_x = ctx.pan_offset_x
        pan_y = ctx.pan_offset_y

        for i, quad in enumerate(overlay.quads):
            if not quad:
                continue
            x0, y0, x1, y1, _cx_px, _cy_px, r_px = quad

            gpu_slot = (
                overlay.gpu_slots[i]
                if is_gpu and i < len(overlay.gpu_slots)
                else None
            )
            if not gpu_slot:
                tid = (
                    widget._feature_overlay_tex_ids[i]
                    if i < len(widget._feature_overlay_tex_ids)
                    else 0
                )
                if not tid:
                    continue

            if gpu_slot:
                combined   = bool(gpu_slot.get("is_combined", False))
                comb_params = None
            else:
                comb_params = (
                    overlay.combined_params[i]
                    if i < len(overlay.combined_params)
                    else None
                )
                combined    = comb_params is not None

            shader = self._get_shader(widget, self._build_key(ctx, gpu_slot, combined))
            if shader is None:
                continue
            pid = shader.programId()
            shader_key = self._build_key(ctx, gpu_slot, combined)

            slot_border_width = (
                float(gpu_slot.get("border_width", overlay.border_width))
                if gpu_slot else float(overlay.border_width)
            )
            border_width = max(0.0, slot_border_width)
            content_radius = max(1.0, r_px - border_width + 1.0)
            if border_width > 0.0:
                slot_border_color = (
                    gpu_slot.get("border_color", overlay.border_color)
                    if gpu_slot else overlay.border_color
                )
                self._draw_slot_frame(
                    widget,
                    ctx,
                    center_x=float(_cx_px),
                    center_y=float(_cy_px),
                    radius=float(r_px),
                    border_width=float(border_width),
                    border_color=_ensure_qcolor(slot_border_color),
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
                gl.glUniform1f(gl.glGetUniformLocation(pid, "diffThreshold"), overlay.gpu_diff_threshold)
                uv1 = gpu_slot.get("uv_rect", (0, 0, 1, 1))
                uv2 = gpu_slot.get("uv_rect2", uv1)
                tex1 = ctx.source_texture_ids[0] if use_source_textures else ctx.texture_ids[0]
                tex2 = ctx.source_texture_ids[1] if use_source_textures else ctx.texture_ids[1]
                gl.glUniform4f(gl.glGetUniformLocation(pid, "uvRect1"), *uv1)
                gl.glUniform4f(gl.glGetUniformLocation(pid, "uvRect2"), *uv2)
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
                gl.glBindTexture(gl.GL_TEXTURE_2D, widget._feature_overlay_tex_ids[i])
                gl.glUniform1i(gl.glGetUniformLocation(pid, "magTex"), 0)
                if combined:
                    comb_tid = (
                        widget._feature_overlay_aux_tex_ids[i]
                        if i < len(widget._feature_overlay_aux_tex_ids)
                        else 0
                    )
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

        end_content_scissor(widget, scissor_enabled)

    def cleanup(self, widget) -> None:
        self._shader_cache.clear()

_BORDER_DISK_FRAG = """
in vec2 TexCoord;
out vec4 FragColor;
uniform vec2 resolution;
uniform vec2 center_px;
uniform float radius_px;
uniform float borderWidth_px;
uniform vec4 color;
void main() {
    vec2 frag_px = TexCoord * resolution;
    float dist = distance(frag_px, center_px);
    float aa = 1.15;
    float outer_alpha = 1.0 - smoothstep(max(0.0, radius_px - aa), radius_px + aa, dist);
    float inner_radius = max(0.0, radius_px - borderWidth_px);
    float inner_alpha = smoothstep(max(0.0, inner_radius - aa), inner_radius + aa, dist);
    float alpha = outer_alpha * inner_alpha;
    if (alpha <= 0.01) discard;
    FragColor = vec4(color.rgb, color.a * alpha);
}
"""

class HiddenSelectionPass(CanvasGLRenderPass):
    stack_role = CanvasStackRole.DEBUG_VIS
    visibility = SceneVisibility.INTERACTIVE

    @staticmethod
    def _resolve_hidden_capture_circles(ctx) -> tuple[object, ...]:
        payloads = (
            ctx.scene_frame.feature_payloads
            if isinstance(getattr(ctx.scene_frame, "feature_payloads", None), dict)
            else {}
        )
        circles = payloads.get("hidden_capture_circles")
        if circles:
            return tuple(circles)
        overlay = getattr(ctx, "feature_overlay", None)
        return tuple(getattr(overlay, "hidden_capture_circles", ()) or ())

    @staticmethod
    def _resolve_hidden_overlay_circles(ctx) -> tuple[object, ...]:
        payloads = (
            ctx.scene_frame.feature_payloads
            if isinstance(getattr(ctx.scene_frame, "feature_payloads", None), dict)
            else {}
        )
        circles = payloads.get("hidden_magnifier_circles")
        if circles:
            return tuple(circles)
        overlay = getattr(ctx, "feature_overlay", None)
        return tuple(getattr(overlay, "hidden_overlay_circles", ()) or ())

    def initialize(self, widget) -> None:
        is_gles = bool(widget.context().isOpenGLES())
        vert_src = f"{_prolog(is_gles)}\n{_ARC_VERT}"
        frag_src = f"{_prolog(is_gles, fragment=True)}\n{_ARC_FRAG}"
        self._shader = _compile(widget, vert_src, frag_src, "HiddenSelectionPass")

    def should_paint(self, ctx) -> bool:
        if is_single_image_preview_scene(ctx):
            return False
        hidden_capture_circles = list(self._resolve_hidden_capture_circles(ctx))
        hidden_overlay_circles = list(self._resolve_hidden_overlay_circles(ctx))
        return bool(hidden_capture_circles or hidden_overlay_circles)

    def paint(self, widget, ctx) -> None:
        if not self._shader or not self._shader.programId():
            return
        hidden_capture_circles = list(self._resolve_hidden_capture_circles(ctx))
        hidden_overlay_circles = list(self._resolve_hidden_overlay_circles(ctx))
        if not hidden_capture_circles and not hidden_overlay_circles:
            return

        pid = self._shader.programId()
        self._shader.bind()
        widget.vao.bind()
        gl.glUniform2f(gl.glGetUniformLocation(pid, "resolution"), float(ctx.width), float(ctx.height))

        stroke_px = max(1.0, float(ctx.resolved_style.annotation_selection_stroke_px))

        def _draw_ring(center, radius, *, active: bool, capture: bool):
            if center is None or radius <= 0:
                return
            cx, cy = widget_px_to_screen_px(widget, center.x(), center.y())
            scaled_radius = float(radius) * ctx.zoom_level
            if scaled_radius <= 0:
                return
            if capture:
                c = QColor(255, 105, 170, 255 if active else 210)
            else:
                c = QColor(70, 190, 255, 255 if active else 210)
            gl.glUniform2f(gl.glGetUniformLocation(pid, "center_px"), float(cx), float(cy))
            gl.glUniform1f(gl.glGetUniformLocation(pid, "radius_px"), float(scaled_radius))
            gl.glUniform1f(gl.glGetUniformLocation(pid, "lineWidth_px"), stroke_px)
            gl.glUniform1f(gl.glGetUniformLocation(pid, "startAngleDeg"), 0.0)
            gl.glUniform1f(gl.glGetUniformLocation(pid, "spanAngleDeg"), 360.0)
            gl.glUniform4f(
                gl.glGetUniformLocation(pid, "color"),
                c.redF(), c.greenF(), c.blueF(), c.alphaF(),
            )
            gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)

        for center, radius, is_active in hidden_capture_circles:
            _draw_ring(center, radius, active=bool(is_active), capture=True)
        for center, radius, is_active in hidden_overlay_circles:
            _draw_ring(center, radius, active=bool(is_active), capture=False)

        widget.vao.release()
        self._shader.release()

    def cleanup(self, widget) -> None:
        self._shader = None

GL_RENDER_PASSES: list[CanvasGLRenderPass] = [
    MagnifierPass(),
    OccludedArcPass(),
    HiddenSelectionPass(),
]
