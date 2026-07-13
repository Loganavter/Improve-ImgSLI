from __future__ import annotations

# File-Size-Exempt: raw GLSL shader source strings for every magnifier pass —
# it's data, not logic; splitting would just scatter one shader's vert/frag
# pair across multiple files for no cohesion gain.

from dataclasses import dataclass

ARC_VERT = """
layout(location = 0) in vec2 aPos;
layout(location = 1) in vec2 aTexCoord;
out vec2 TexCoord;
void main() {
    gl_Position = vec4(aPos, 0.0, 1.0);
    TexCoord = aTexCoord;
}
"""

ARC_FRAG = """
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

MAG_VERT = """
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

MAG_FRAG = """
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

BORDER_DISK_FRAG = """
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


@dataclass(frozen=True, slots=True)
class MagShaderKey:
    gpu_sampling: bool
    combined: bool
    interp_mode: int = 1
    diff_mode: int = 0
    channel_mode: int = 0
    source_mode: int = 0


def _norm(mode: int, valid: tuple[int, ...], default: int) -> int:
    return mode if mode in valid else default


def build_mag_frag(key: MagShaderKey, *, is_gles: bool) -> str:
    gpu_sampling = bool(key.gpu_sampling)
    combined = bool(key.combined)
    interp = _norm(key.interp_mode if gpu_sampling else 1, (0, 1, 2, 3, 4), 1)
    channel = _norm(key.channel_mode, (0, 1, 2, 3, 4), 0)
    source = _norm(
        key.source_mode if gpu_sampling and not combined else 0,
        (0, 1, 2),
        0,
    )
    diff = _norm(
        key.diff_mode if gpu_sampling and not combined and source == 2 else 0,
        (0, 1, 2, 3, 4),
        0,
    )

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
    if gpu_sampling:
        header.append("#define MAG_GPU_SAMPLING 1")
    if combined:
        header.append("#define MAG_COMBINED 1")
    header.append(f"#define MAG_INTERP_MODE {interp}")
    header.append(f"#define MAG_DIFF_MODE {diff}")
    header.append(f"#define MAG_CHANNEL_MODE {channel}")
    header.append(f"#define MAG_SOURCE_MODE {source}")
    header.append(MAG_FRAG)
    return "\n".join(header)
