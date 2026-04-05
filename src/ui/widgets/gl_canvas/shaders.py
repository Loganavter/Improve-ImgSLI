from dataclasses import dataclass

def _shader_prolog(is_gles: bool, *, fragment: bool = False) -> str:
    if not is_gles:
        return "#version 330 core"
    lines = ["#version 300 es", "precision highp float;", "precision highp int;"]
    if fragment:
        lines.append("precision mediump sampler2D;")
    return "\n".join(lines)

BASE_VERTEX_SHADER_TEMPLATE = """
layout (location = 0) in vec2 aPos;
layout (location = 1) in vec2 aTexCoord;
out vec2 TexCoord;
void main() {
    gl_Position = vec4(aPos.x, aPos.y, 0.0, 1.0);
    TexCoord = aTexCoord;
}
"""

BASE_FRAGMENT_SHADER_TEMPLATE = """
in vec2 TexCoord;
out vec4 FragColor;

uniform float splitPosition;
uniform bool isHorizontal;
uniform bool showDivider;
uniform vec4 dividerColor;
uniform float dividerThickness;
uniform vec4 dividerClip; // x0, y0, x1, y1 in widget/image UV
uniform vec2 offset;
uniform float zoom;

uniform sampler2D image1;
uniform sampler2D image2;
uniform int channelMode; // 0=RGB, 1=R, 2=G, 3=B, 4=L
uniform bool useSourceTex;
uniform vec4 letterbox1; // offsetX, offsetY, scaleX, scaleY
uniform vec4 letterbox2; // offsetX, offsetY, scaleX, scaleY

vec4 applyChannel(vec4 c, int mode) {
    if (mode == 1) return vec4(c.r, 0.0, 0.0, c.a);
    if (mode == 2) return vec4(0.0, c.g, 0.0, c.a);
    if (mode == 3) return vec4(0.0, 0.0, c.b, c.a);
    if (mode == 4) { float l = dot(c.rgb, vec3(0.299, 0.587, 0.114)); return vec4(l, l, l, c.a); }
    return c;
}

void main() {
    vec2 center = vec2(0.5, 0.5);
    vec2 uv = (TexCoord - center) / zoom + center - offset;

    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
        FragColor = vec4(0.0, 0.0, 0.0, 0.0);
        return;
    }

    vec4 color;
    float coord = isHorizontal ? TexCoord.y : TexCoord.x;
    bool useFirst = coord < splitPosition;
    vec4 letterbox = useFirst ? letterbox1 : letterbox2;
    vec2 sampleUV = (uv - letterbox.xy) / letterbox.zw;
    if (sampleUV.x < 0.0 || sampleUV.x > 1.0 || sampleUV.y < 0.0 || sampleUV.y > 1.0) {
        FragColor = vec4(0.0, 0.0, 0.0, 0.0);
        return;
    }

    if (useFirst) {
        color = texture(image1, sampleUV);
    } else {
        color = texture(image2, sampleUV);
    }

    color = applyChannel(color, channelMode);

    bool insideDividerClip =
        uv.x >= dividerClip.x && uv.x <= dividerClip.z &&
        uv.y >= dividerClip.y && uv.y <= dividerClip.w;

    if (showDivider && insideDividerClip && color.a > 0.001 && abs(coord - splitPosition) < dividerThickness) {
        color = mix(color, dividerColor, dividerColor.a);
    }

    FragColor = color;
}
"""

MAGNIFIER_VERTEX_SHADER_TEMPLATE = """
layout(location = 0) in vec2 aPos;
layout(location = 1) in vec2 aTexCoord;
uniform vec4 quadBounds; // xMin, yMin, xMax, yMax in NDC
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

def build_base_vertex_shader(is_gles: bool) -> str:
    return f"{_shader_prolog(is_gles)}\n{BASE_VERTEX_SHADER_TEMPLATE}"

def build_base_fragment_shader(is_gles: bool) -> str:
    return f"{_shader_prolog(is_gles, fragment=True)}\n{BASE_FRAGMENT_SHADER_TEMPLATE}"

def build_magnifier_vertex_shader(is_gles: bool) -> str:
    return f"{_shader_prolog(is_gles)}\n{MAGNIFIER_VERTEX_SHADER_TEMPLATE}"

@dataclass(frozen=True, slots=True)
class MagnifierShaderVariantKey:
    gpu_sampling: bool
    combined: bool
    interp_mode: int = 1
    diff_mode: int = 0
    channel_mode: int = 0
    source_mode: int = 0

def _normalize_interp_mode(mode: int) -> int:
    return mode if mode in (0, 1, 2, 3, 4) else 1

def _normalize_diff_mode(mode: int) -> int:
    return mode if mode in (0, 1, 2, 3, 4) else 0

def _normalize_channel_mode(mode: int) -> int:
    return mode if mode in (0, 1, 2, 3, 4) else 0

def _normalize_source_mode(mode: int) -> int:
    return mode if mode in (0, 1, 2) else 0

def build_magnifier_fragment_shader(key: MagnifierShaderVariantKey, *, is_gles: bool = False) -> str:
    combined = bool(key.combined)
    gpu_sampling = bool(key.gpu_sampling)
    interp_mode = _normalize_interp_mode(key.interp_mode if gpu_sampling else 1)
    channel_mode = _normalize_channel_mode(key.channel_mode)
    source_mode = _normalize_source_mode(key.source_mode if gpu_sampling and not combined else 0)
    diff_mode = _normalize_diff_mode(
        key.diff_mode if gpu_sampling and not combined and source_mode == 2 else 0
    )

    defines = ["#version 300 es" if is_gles else "#version 330 core"]
    if is_gles:
        defines.extend(
            [
                "#ifdef GL_OES_standard_derivatives",
                "#extension GL_OES_standard_derivatives : enable",
                "#endif",
                "precision highp float;",
                "precision highp int;",
                "precision mediump sampler2D;",
            ]
        )
    else:
        defines.extend(
            [
                "#ifdef GL_OES_standard_derivatives",
                "#extension GL_OES_standard_derivatives : enable",
                "#endif",
            ]
        )
    if gpu_sampling:
        defines.append("#define MAG_GPU_SAMPLING 1")
    if combined:
        defines.append("#define MAG_COMBINED 1")
    defines.append(f"#define MAG_INTERP_MODE {interp_mode}")
    defines.append(f"#define MAG_DIFF_MODE {diff_mode}")
    defines.append(f"#define MAG_CHANNEL_MODE {channel_mode}")
    defines.append(f"#define MAG_SOURCE_MODE {source_mode}")
    defines.append(MAGNIFIER_FRAGMENT_SHADER_TEMPLATE)
    return "\n".join(defines)

MAGNIFIER_FRAGMENT_SHADER_TEMPLATE = """
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

float luminance(vec3 c) {
    return dot(c, vec3(0.299, 0.587, 0.114));
}

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
    vec2 pos = uv * texSize - 0.5;
    vec2 base = floor(pos);
    vec2 f = fract(pos);
    vec4 result = vec4(0.0);
    float totalWeight = 0.0;
    for (int j = -1; j <= 2; j++) {
        float wy = cubicWeight(float(j) - f.y);
        for (int k = -1; k <= 2; k++) {
            float wx = cubicWeight(float(k) - f.x);
            float w = wx * wy;
            ivec2 sampleTexel = ivec2(base) + ivec2(k, j);
            sampleTexel = clamp(sampleTexel, ivec2(0), texSizeI - ivec2(1));
            result += texelFetch(tex, sampleTexel, 0) * w;
            totalWeight += w;
        }
    }
    if (totalWeight <= 0.0) {
        ivec2 fallbackTexel = clamp(ivec2(round(pos)), ivec2(0), texSizeI - ivec2(1));
        return texelFetch(tex, fallbackTexel, 0);
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
    vec2 pos = uv * texSize - 0.5;
    ivec2 base = ivec2(floor(pos));
    vec2 f = fract(pos);
    vec4 result = vec4(0.0);
    float totalWeight = 0.0;
    for (int j = -2; j <= 3; j++) {
        float wy = lanczosWeight(float(j) - f.y, A);
        for (int k = -2; k <= 3; k++) {
            float wx = lanczosWeight(float(k) - f.x, A);
            float w = wx * wy;
            if (w == 0.0) continue;
            ivec2 sampleTexel = clamp(base + ivec2(k, j), ivec2(0), texSizeI - ivec2(1));
            result += texelFetch(tex, sampleTexel, 0) * w;
            totalWeight += w;
        }
    }
    if (totalWeight <= 0.0) {
        ivec2 fallbackTexel = clamp(ivec2(round(pos)), ivec2(0), texSizeI - ivec2(1));
        return texelFetch(tex, fallbackTexel, 0);
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

    float det = footprint[0][0] * footprint[1][1] - footprint[0][1] * footprint[1][0];
    if (det <= 1e-6) {
        return sampleLanczos(tex, uv);
    }

    mat2 invFootprint = mat2(
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
            float r2 = dot(d, invFootprint * d);
            if (r2 >= A * A) continue;
            float w = lanczosWeight(sqrt(r2), A);
            if (w == 0.0) continue;
            ivec2 sampleTexel = clamp(center + ivec2(k, j), ivec2(0), texSizeI - ivec2(1));
            result += texelFetch(tex, sampleTexel, 0) * w;
            totalWeight += w;
        }
    }

    if (totalWeight <= 0.0) {
        return sampleLanczos(tex, uv);
    }
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
    vec2 uv;
    vec4 c;
    if (source == 0) {
        uv = mix(uvRect1.xy, uvRect1.zw, tc);
        c = sampleInterp(bgTex1, uv);
    } else if (source == 1) {
        uv = mix(uvRect2.xy, uvRect2.zw, tc);
        c = sampleInterp(bgTex2, uv);
    } else {
        uv = mix(uvRect1.xy, uvRect1.zw, tc);
        c = sampleInterp(bgTexDiff, uv);
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
    vec4 c1 = sampleInterp(bgTex1, uv1);
    vec4 c2 = sampleInterp(bgTex2, uv2);

#if MAG_DIFF_MODE == 1
    vec3 diff = abs(c1.rgb - c2.rgb);
    float maxDiff = max(diff.r, max(diff.g, diff.b));
    if (maxDiff > diffThreshold) {
        return vec4(1.0, 0.35, 0.47, 1.0);
    }
    return applyChannel(c1);
#elif MAG_DIFF_MODE == 2
    vec3 diff = abs(c1.rgb - c2.rgb);
    float g = luminance(diff);
    g = clamp(g * 4.0, 0.0, 1.0);
    return vec4(g, g, g, 1.0);
#elif MAG_DIFF_MODE == 3
    vec2 uv = mix(uvRect1.xy, uvRect1.zw, tc);
    vec2 step = (uvRect1.zw - uvRect1.xy) / vec2(textureSize(bgTex1, 0));
    float tl = luminance(texture(bgTex1, uv + vec2(-step.x, -step.y)).rgb);
    float t  = luminance(texture(bgTex1, uv + vec2(0.0,     -step.y)).rgb);
    float tr = luminance(texture(bgTex1, uv + vec2( step.x, -step.y)).rgb);
    float l  = luminance(texture(bgTex1, uv + vec2(-step.x,  0.0)).rgb);
    float r  = luminance(texture(bgTex1, uv + vec2( step.x,  0.0)).rgb);
    float bl = luminance(texture(bgTex1, uv + vec2(-step.x,  step.y)).rgb);
    float b  = luminance(texture(bgTex1, uv + vec2(0.0,      step.y)).rgb);
    float br = luminance(texture(bgTex1, uv + vec2( step.x,  step.y)).rgb);
    float gx = -tl - 2.0*l - bl + tr + 2.0*r + br;
    float gy = -tl - 2.0*t - tr + bl + 2.0*b + br;
    float edge = sqrt(gx*gx + gy*gy);
    edge = smoothstep(0.05, 0.3, edge);
    return vec4(edge, edge, edge, 1.0);
#elif MAG_DIFF_MODE == 4
    vec2 uv = mix(uvRect1.xy, uvRect1.zw, tc);
    vec4 c = sampleInterp(bgTexDiff, uv);
    return applyChannel(c);
#else
    return applyChannel(c1);
#endif
}

void main() {
    vec4 col;

#ifdef MAG_GPU_SAMPLING
    #ifdef MAG_COMBINED
        float coord = combHorizontal ? TexCoord.y : TexCoord.x;
        if (coord < internalSplit) {
            col = sampleBgFromSource(0, TexCoord);
        } else {
            col = sampleBgFromSource(1, TexCoord);
        }
        if (showCombDivider && combDividerThickness > 0.0) {
            float dist = abs(coord - internalSplit);
            if (dist < combDividerThickness) {
                col = mix(col, combDividerColor, combDividerColor.a);
            }
        }
    #elif MAG_SOURCE_MODE == 2 && MAG_DIFF_MODE != 0
        col = computeDiff(TexCoord);
    #else
        col = sampleSelectedBg(TexCoord);
    #endif
#else
    #ifdef MAG_COMBINED
        float coord = combHorizontal ? TexCoord.y : TexCoord.x;
        if (coord < internalSplit) {
            col = texture(magTex, TexCoord);
        } else {
            col = texture(magTex2, TexCoord);
        }
        if (showCombDivider && combDividerThickness > 0.0) {
            float dist = abs(coord - internalSplit);
            if (dist < combDividerThickness) {
                col = mix(col, combDividerColor, combDividerColor.a);
            }
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

        float border_mask = smoothstep(0.42, 0.92, outer_mask);
        float border_alpha = border_mask * borderColor.a;
        float fill_alpha = col.a * inner_mask;

        float out_alpha = fill_alpha + border_alpha * (1.0 - fill_alpha);
        if (out_alpha <= 0.001) discard;

        vec3 out_rgb =
            (col.rgb * fill_alpha + borderColor.rgb * border_alpha * (1.0 - fill_alpha))
            / out_alpha;

        col.rgb = out_rgb;
        col.a = out_alpha;
    }
    FragColor = col;
}
"""

CIRCLE_VERTEX_SHADER_TEMPLATE = """
layout(location = 0) in vec2 aPos;
layout(location = 1) in vec2 aTexCoord;
out vec2 TexCoord;
void main() {
    gl_Position = vec4(aPos, 0.0, 1.0);
    TexCoord = aTexCoord;
}
"""

CIRCLE_FRAGMENT_SHADER_TEMPLATE = """
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
    float outer = 1.0 - smoothstep(radius_px + half_w - aa, radius_px + half_w + aa, dist);
    float inner = 1.0 - smoothstep(radius_px - half_w - aa, radius_px - half_w + aa, dist);
    float ring = clamp(outer - inner, 0.0, 1.0);
    if (ring <= 0.01) discard;
    FragColor = vec4(color.rgb, color.a * ring);
}
"""

def build_circle_vertex_shader(is_gles: bool) -> str:
    return f"{_shader_prolog(is_gles)}\n{CIRCLE_VERTEX_SHADER_TEMPLATE}"

def build_circle_fragment_shader(is_gles: bool) -> str:
    return f"{_shader_prolog(is_gles, fragment=True)}\n{CIRCLE_FRAGMENT_SHADER_TEMPLATE}"
