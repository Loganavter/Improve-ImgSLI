#version 440

layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;
    vec4 quadBounds;
    vec2 magPan;
    vec2 _pad0;
    float magZoom;
    float radius_px;
    float borderWidth;
    float internalSplit;
    vec4 borderColor;
    vec4 combDividerColor;
    float combDividerThickness;
    float diffThreshold;
    int   combHorizontal;
    int   showCombDivider;
    int   useCircleMask;
    int   magGpuSampling;
    int   magCombined;
    int   magSourceMode;
    int   magDiffMode;
    int   magChannelMode;
    int   magInterpMode;
    int   _pad1;
    vec4 uvRect1;
    vec4 uvRect2;
};

layout(binding = 1) uniform sampler2D bgTex1;
layout(binding = 2) uniform sampler2D bgTex2;
layout(binding = 3) uniform sampler2D bgTexDiff;
layout(binding = 4) uniform sampler2D circleMaskTex;
layout(binding = 5) uniform sampler2D magTex;
layout(binding = 6) uniform sampler2D magTex2;

layout(location = 0) in vec2 TexCoord;
layout(location = 0) out vec4 FragColor;

float luminance(vec3 c) { return dot(c, vec3(0.299, 0.587, 0.114)); }

vec4 applyChannel(vec4 c) {
    if (magChannelMode == 1) return vec4(c.r, 0.0, 0.0, c.a);
    if (magChannelMode == 2) return vec4(0.0, c.g, 0.0, c.a);
    if (magChannelMode == 3) return vec4(0.0, 0.0, c.b, c.a);
    if (magChannelMode == 4) { float l = luminance(c.rgb); return vec4(l, l, l, c.a); }
    return c;
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

vec4 sampleEwaLanczos(sampler2D tex, vec2 uv, vec2 ddx, vec2 ddy) {
    const float A = 3.0;
    const int MAX_RADIUS = 6;
    ivec2 texSizeI = textureSize(tex, 0);
    vec2 texSize = vec2(texSizeI);
    vec2 pos = uv * texSize - 0.5;
    vec2 dx = ddx * texSize;
    vec2 dy = ddy * texSize;
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

vec4 sampleInterp(sampler2D tex, vec2 uv, vec2 ddx, vec2 ddy) {
    if (magInterpMode == 0) return sampleNearest(tex, uv);
    if (magInterpMode == 2) return sampleBicubic(tex, uv);
    if (magInterpMode == 3) return sampleLanczos(tex, uv);
    if (magInterpMode == 4) return sampleEwaLanczos(tex, uv, ddx, ddy);
    return texture(tex, uv);
}

vec4 sampleBgFromSource(int source, vec2 tc, vec2 ddx_tc, vec2 ddy_tc) {
    vec2 uv; vec4 c;
    vec2 ddx; vec2 ddy;
    if (source == 0) {
        uv = mix(uvRect1.xy, uvRect1.zw, tc);
        ddx = (uvRect1.zw - uvRect1.xy) * ddx_tc;
        ddy = (uvRect1.zw - uvRect1.xy) * ddy_tc;
        c  = sampleInterp(bgTex1, uv, ddx, ddy);
    } else if (source == 1) {
        uv = mix(uvRect2.xy, uvRect2.zw, tc);
        ddx = (uvRect2.zw - uvRect2.xy) * ddx_tc;
        ddy = (uvRect2.zw - uvRect2.xy) * ddy_tc;
        c  = sampleInterp(bgTex2, uv, ddx, ddy);
    } else {
        uv = mix(uvRect1.xy, uvRect1.zw, tc);
        ddx = (uvRect1.zw - uvRect1.xy) * ddx_tc;
        ddy = (uvRect1.zw - uvRect1.xy) * ddy_tc;
        c  = sampleInterp(bgTexDiff, uv, ddx, ddy);
    }
    return applyChannel(c);
}

vec4 sampleSelectedBg(vec2 tc, vec2 ddx, vec2 ddy) {
    if (magSourceMode == 1) return sampleBgFromSource(1, tc, ddx, ddy);
    if (magSourceMode == 2) return sampleBgFromSource(2, tc, ddx, ddy);
    return sampleBgFromSource(0, tc, ddx, ddy);
}

vec4 computeDiff(vec2 tc, vec2 ddx_tc, vec2 ddy_tc) {
    vec2 uv1 = mix(uvRect1.xy, uvRect1.zw, tc);
    vec2 uv2 = mix(uvRect2.xy, uvRect2.zw, tc);
    vec2 ddx1 = (uvRect1.zw - uvRect1.xy) * ddx_tc;
    vec2 ddy1 = (uvRect1.zw - uvRect1.xy) * ddy_tc;
    vec2 ddx2 = (uvRect2.zw - uvRect2.xy) * ddx_tc;
    vec2 ddy2 = (uvRect2.zw - uvRect2.xy) * ddy_tc;
    vec4 c1  = sampleInterp(bgTex1, uv1, ddx1, ddy1);
    vec4 c2  = sampleInterp(bgTex2, uv2, ddx2, ddy2);
    if (magDiffMode == 1) {
        vec3 diff = abs(c1.rgb - c2.rgb);
        float maxDiff = max(diff.r, max(diff.g, diff.b));
        if (maxDiff > diffThreshold) { return vec4(1.0, 0.35, 0.47, 1.0); }
        return applyChannel(c1);
    }
    if (magDiffMode == 2) {
        vec3 diff = abs(c1.rgb - c2.rgb);
        float g = clamp(luminance(diff) * 4.0, 0.0, 1.0);
        return vec4(g, g, g, 1.0);
    }
    if (magDiffMode == 3) {
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
    }
    if (magDiffMode == 4) {
        vec2 uv = mix(uvRect1.xy, uvRect1.zw, tc);
        return applyChannel(sampleInterp(bgTexDiff, uv, ddx1, ddy1));
    }
    return applyChannel(c1);
}

void main()
{
    vec2 ddx_tc = dFdx(TexCoord);
    vec2 ddy_tc = dFdy(TexCoord);

    vec4 col;
    if (magGpuSampling != 0) {
        if (magCombined != 0) {
            float coord = (combHorizontal != 0) ? TexCoord.y : TexCoord.x;
            col = (coord < internalSplit)
                ? sampleBgFromSource(0, TexCoord, ddx_tc, ddy_tc)
                : sampleBgFromSource(1, TexCoord, ddx_tc, ddy_tc);
            if (showCombDivider != 0 && combDividerThickness > 0.0) {
                float dist = abs(coord - internalSplit);
                if (dist < combDividerThickness) {
                    col = mix(col, combDividerColor, combDividerColor.a);
                }
            }
        } else if (magSourceMode == 2 && magDiffMode != 0) {
            col = computeDiff(TexCoord, ddx_tc, ddy_tc);
        } else {
            col = sampleSelectedBg(TexCoord, ddx_tc, ddy_tc);
        }
    } else {
        if (magCombined != 0) {
            float coord = (combHorizontal != 0) ? TexCoord.y : TexCoord.x;
            col = (coord < internalSplit)
                ? texture(magTex, TexCoord)
                : texture(magTex2, TexCoord);
            if (showCombDivider != 0 && combDividerThickness > 0.0) {
                float dist = abs(coord - internalSplit);
                if (dist < combDividerThickness) {
                    col = mix(col, combDividerColor, combDividerColor.a);
                }
            }
        } else {
            col = texture(magTex, TexCoord);
        }
    }

    if (useCircleMask != 0) {
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
