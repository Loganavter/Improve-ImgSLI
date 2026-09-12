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
    int   magLayer1;
    int   magLayer2;
    int   magLayerDiff;
    int   _pad1;
    int   _pad2;
    vec4 uvRect1;
    vec4 uvRect2;
    vec4 magContentScale12;
    vec4 magContentScaleDiffPad;
    vec4 clipRect;
};

layout(binding = 1) uniform sampler2DArray bgArray;
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

vec4 sampleNearest(int layer, vec2 uv, ivec2 texSize, ivec2 contentSize) {
    vec2 texelPos = uv * vec2(texSize) - 0.5;
    ivec2 texel = ivec2(round(texelPos));
    texel = clamp(texel, ivec2(0), contentSize - ivec2(1));
    return texelFetch(bgArray, ivec3(texel, layer), 0);
}

float cubicWeight(float x) {
    float ax = abs(x);
    if (ax <= 1.0) return (1.5*ax - 2.5)*ax*ax + 1.0;
    if (ax <= 2.0) return ((-0.5*ax + 2.5)*ax - 4.0)*ax + 2.0;
    return 0.0;
}

vec4 sampleBicubic(int layer, vec2 uv, ivec2 texSizeI, ivec2 contentSizeI) {
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
            ivec2 sampleTexel = clamp(ivec2(base) + ivec2(k, j), ivec2(0), contentSizeI - ivec2(1));
            result += texelFetch(bgArray, ivec3(sampleTexel, layer), 0) * w;
            totalWeight += w;
        }
    }
    if (totalWeight <= 0.0) {
        ivec2 fb = clamp(ivec2(round(pos)), ivec2(0), contentSizeI - ivec2(1));
        return texelFetch(bgArray, ivec3(fb, layer), 0);
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

vec4 sampleLanczos(int layer, vec2 uv, ivec2 texSizeI, ivec2 contentSizeI) {
    const float A = 3.0;
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
            ivec2 st = clamp(base + ivec2(k, j), ivec2(0), contentSizeI - ivec2(1));
            result += texelFetch(bgArray, ivec3(st, layer), 0) * w;
            totalWeight += w;
        }
    }
    if (totalWeight <= 0.0) {
        ivec2 fb = clamp(ivec2(round(pos)), ivec2(0), contentSizeI - ivec2(1));
        return texelFetch(bgArray, ivec3(fb, layer), 0);
    }
    return result / totalWeight;
}

vec4 sampleEwaLanczos(int layer, vec2 uv, vec2 ddx, vec2 ddy, ivec2 texSizeI, ivec2 contentSizeI) {
    const float A = 3.0;
    const int MAX_RADIUS = 6;
    vec2 texSize = vec2(texSizeI);
    vec2 pos = uv * texSize - 0.5;
    vec2 dx = ddx * texSize;
    vec2 dy = ddy * texSize;
    mat2 footprint = mat2(
        dot(dx, dx) + 1.0, dot(dx, dy),
        dot(dx, dy), dot(dy, dy) + 1.0
    );
    float det = footprint[0][0]*footprint[1][1] - footprint[0][1]*footprint[1][0];
    if (det <= 1e-6) { return sampleLanczos(layer, uv, texSizeI, contentSizeI); }
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
            ivec2 st = clamp(center + ivec2(k, j), ivec2(0), contentSizeI - ivec2(1));
            result += texelFetch(bgArray, ivec3(st, layer), 0) * w;
            totalWeight += w;
        }
    }
    if (totalWeight <= 0.0) { return sampleLanczos(layer, uv, texSizeI, contentSizeI); }
    return result / totalWeight;
}

// Manual bilinear, clamped to the tile's own content bounds -- the default
// interpolation mode (``magInterpMode`` outside 0/2/3/4, i.e. "linear")
// used to fall through to the hardware ``texture()`` sampler. That sampler
// is set to ClampToEdge (see MagnifierPass.initialize), but ClampToEdge
// only stops wraparound at the *array layer's* true 0/1 edges -- it has no
// idea the tile's real content ends earlier, at content_scale, so its own
// bilinear filtering still blends the last real content texel with the
// first padding texel right at that boundary. Since "linear" is
// gpu_interp_mode's actual default, this was the sampling path most users
// hit, and it was untouched by sampleNearest/Bicubic/Lanczos/EwaLanczos's
// own contentSize clamp above.
vec4 sampleBilinear(int layer, vec2 uv, ivec2 texSize, ivec2 contentSize) {
    vec2 texelPos = uv * vec2(texSize) - 0.5;
    ivec2 base = ivec2(floor(texelPos));
    vec2 f = fract(texelPos);
    ivec2 c00 = clamp(base + ivec2(0, 0), ivec2(0), contentSize - ivec2(1));
    ivec2 c10 = clamp(base + ivec2(1, 0), ivec2(0), contentSize - ivec2(1));
    ivec2 c01 = clamp(base + ivec2(0, 1), ivec2(0), contentSize - ivec2(1));
    ivec2 c11 = clamp(base + ivec2(1, 1), ivec2(0), contentSize - ivec2(1));
    vec4 v00 = texelFetch(bgArray, ivec3(c00, layer), 0);
    vec4 v10 = texelFetch(bgArray, ivec3(c10, layer), 0);
    vec4 v01 = texelFetch(bgArray, ivec3(c01, layer), 0);
    vec4 v11 = texelFetch(bgArray, ivec3(c11, layer), 0);
    vec4 top = mix(v00, v10, f.x);
    vec4 bot = mix(v01, v11, f.x);
    return mix(top, bot, f.y);
}

// ``uv`` is already normalized against the *full* array layer (callers do
// ``contentRelativeUV * contentScale`` before this, so it lands in
// ``[0, contentScale]`` of the full-layer [0,1] range) -- ``texSize`` (the
// full layer's own pixel size) is what correctly turns that back into a
// texel position, same as it always was. ``contentSize`` (layer size *
// content_scale) is only for *clamping* the kernel taps: tiles upload
// unresampled 1:1 into a layer's top-left corner (see array_resources.py's
// upload_tile_to_array), so anything beyond content_scale within that same
// layer is padding/leftover-previous-tile data, and the non-nearest kernels
// below sample several neighboring texels -- clamping their taps to the
// full layer size (as this used to, and as an earlier one-parameter version
// of this fix incorrectly still did by reusing texSize for both jobs) let
// them read into that padding near a tile's real edge -- exactly where
// panning across a tile boundary would show it, as wrong/black pixels
// ("holes") that got worse the wider the kernel (EWA's radius-6 taps most
// of all).
vec4 sampleInterp(int layer, vec2 uv, vec2 ddx, vec2 ddy, ivec2 texSize, ivec2 contentSize) {
    if (magInterpMode == 0) return sampleNearest(layer, uv, texSize, contentSize);
    if (magInterpMode == 2) return sampleBicubic(layer, uv, texSize, contentSize);
    if (magInterpMode == 3) return sampleLanczos(layer, uv, texSize, contentSize);
    if (magInterpMode == 4) return sampleEwaLanczos(layer, uv, ddx, ddy, texSize, contentSize);
    return sampleBilinear(layer, uv, texSize, contentSize);
}

vec4 sampleBgFromSource(int source, vec2 tc, vec2 ddx_tc, vec2 ddy_tc) {
    vec2 uv; vec4 c;
    vec2 ddx; vec2 ddy;
    int layer; vec2 scale;
    ivec2 arraySize = textureSize(bgArray, 0).xy;
    if (source == 0) {
        layer = magLayer1;
        scale = magContentScale12.xy;
        // Clamp the tile-local (pre-scale) uv to [0,1] before scaling into
        // layer space: uvRect1 is extrapolated (see
        // expand_uv_rect_to_absolute_tc) so mix() only lands in [0,1] for
        // tc strictly inside this record's own scissor window -- but the
        // GPU scissor test is pixel-quantized while tc is a continuous
        // per-fragment interpolation, so fragments right at a tile
        // boundary can carry a tc a hair outside that window. For a
        // capture split across many tiles that window is narrow, so the
        // extrapolation slope is steep and even that sub-pixel tc error
        // blows up into a uv landing well past this tile's real content,
        // into the array layer's stale padding/leftover-previous-tile
        // data (a genuinely different, unrelated tile's old pixels) --
        // that's the "random other tile" garbage. Clamping pins any such
        // overshoot to this tile's own edge instead.
        uv = clamp(mix(uvRect1.xy, uvRect1.zw, tc), 0.0, 1.0) * scale;
        ddx = (uvRect1.zw - uvRect1.xy) * ddx_tc * scale;
        ddy = (uvRect1.zw - uvRect1.xy) * ddy_tc * scale;
        c  = sampleInterp(layer, uv, ddx, ddy, arraySize, ivec2(round(vec2(arraySize) * scale)));
    } else if (source == 1) {
        layer = magLayer2;
        scale = magContentScale12.zw;
        uv = clamp(mix(uvRect2.xy, uvRect2.zw, tc), 0.0, 1.0) * scale;
        ddx = (uvRect2.zw - uvRect2.xy) * ddx_tc * scale;
        ddy = (uvRect2.zw - uvRect2.xy) * ddy_tc * scale;
        c  = sampleInterp(layer, uv, ddx, ddy, arraySize, ivec2(round(vec2(arraySize) * scale)));
    } else {
        layer = magLayerDiff;
        scale = magContentScaleDiffPad.xy;
        uv = clamp(mix(uvRect1.xy, uvRect1.zw, tc), 0.0, 1.0) * scale;
        ddx = (uvRect1.zw - uvRect1.xy) * ddx_tc * scale;
        ddy = (uvRect1.zw - uvRect1.xy) * ddy_tc * scale;
        c  = sampleInterp(layer, uv, ddx, ddy, arraySize, ivec2(round(vec2(arraySize) * scale)));
    }
    return applyChannel(c);
}

vec4 sampleSelectedBg(vec2 tc, vec2 ddx, vec2 ddy) {
    if (magSourceMode == 1) return sampleBgFromSource(1, tc, ddx, ddy);
    if (magSourceMode == 2) return sampleBgFromSource(2, tc, ddx, ddy);
    return sampleBgFromSource(0, tc, ddx, ddy);
}

vec4 computeDiff(vec2 tc, vec2 ddx_tc, vec2 ddy_tc) {
    vec2 scale1 = magContentScale12.xy;
    vec2 scale2 = magContentScale12.zw;
    vec2 uv1 = clamp(mix(uvRect1.xy, uvRect1.zw, tc), 0.0, 1.0) * scale1;
    vec2 uv2 = clamp(mix(uvRect2.xy, uvRect2.zw, tc), 0.0, 1.0) * scale2;
    vec2 ddx1 = (uvRect1.zw - uvRect1.xy) * ddx_tc * scale1;
    vec2 ddy1 = (uvRect1.zw - uvRect1.xy) * ddy_tc * scale1;
    vec2 ddx2 = (uvRect2.zw - uvRect2.xy) * ddx_tc * scale2;
    vec2 ddy2 = (uvRect2.zw - uvRect2.xy) * ddy_tc * scale2;
    ivec2 arraySize = textureSize(bgArray, 0).xy;
    vec4 c1  = sampleInterp(magLayer1, uv1, ddx1, ddy1, arraySize, ivec2(round(vec2(arraySize) * scale1)));
    vec4 c2  = sampleInterp(magLayer2, uv2, ddx2, ddy2, arraySize, ivec2(round(vec2(arraySize) * scale2)));
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
        vec2 uv   = uv1;
        vec2 step = ((uvRect1.zw - uvRect1.xy) * scale1) / vec2(textureSize(bgArray, 0).xy);
        float tl = luminance(texture(bgArray, vec3(uv + vec2(-step.x, -step.y), magLayer1)).rgb);
        float t  = luminance(texture(bgArray, vec3(uv + vec2( 0.0,    -step.y), magLayer1)).rgb);
        float tr = luminance(texture(bgArray, vec3(uv + vec2( step.x, -step.y), magLayer1)).rgb);
        float l  = luminance(texture(bgArray, vec3(uv + vec2(-step.x,  0.0   ), magLayer1)).rgb);
        float r  = luminance(texture(bgArray, vec3(uv + vec2( step.x,  0.0   ), magLayer1)).rgb);
        float bl = luminance(texture(bgArray, vec3(uv + vec2(-step.x,  step.y), magLayer1)).rgb);
        float b  = luminance(texture(bgArray, vec3(uv + vec2( 0.0,     step.y), magLayer1)).rgb);
        float br = luminance(texture(bgArray, vec3(uv + vec2( step.x,  step.y), magLayer1)).rgb);
        float gx = -tl - 2.0*l - bl + tr + 2.0*r + br;
        float gy = -tl - 2.0*t - tr + bl + 2.0*b + br;
        float edge = smoothstep(0.05, 0.3, sqrt(gx*gx + gy*gy));
        return vec4(edge, edge, edge, 1.0);
    }
    if (magDiffMode == 4) {
        vec2 scaleD = magContentScaleDiffPad.xy;
        vec2 uv = clamp(mix(uvRect1.xy, uvRect1.zw, tc), 0.0, 1.0) * scaleD;
        vec2 ddxD = (uvRect1.zw - uvRect1.xy) * ddx_tc * scaleD;
        vec2 ddyD = (uvRect1.zw - uvRect1.xy) * ddy_tc * scaleD;
        return applyChannel(sampleInterp(magLayerDiff, uv, ddxD, ddyD, arraySize, ivec2(round(vec2(arraySize) * scaleD))));
    }
    return applyChannel(c1);
}

void main()
{
    vec2 ddx_tc = dFdx(TexCoord);
    vec2 ddy_tc = dFdy(TexCoord);

    // Per-record clip in tc space, replacing GPU scissor state for
    // multi-tile magnifier captures: each tile-record draw call used to
    // rely on `command_buffer.setScissor()` changing between consecutive
    // draw() calls within one pass to confine it to its own tc sub-window
    // -- confirmed (by forcing every draw to bind the same uniform slot
    // while keeping distinct scissors, and seeing only one tile's content
    // instead of it tiled across every scissor region) not to reliably
    // take effect per draw call. `clipRect` is (tcXLo, tcYLo, tcXHi,
    // tcYHi) for this record; discard-based clipping lives entirely in
    // per-fragment data instead of GPU pipeline state, so it can't go
    // stale between draw calls the way scissor state did.
    if (
        TexCoord.x < clipRect.x || TexCoord.x > clipRect.z ||
        TexCoord.y < clipRect.y || TexCoord.y > clipRect.w
    ) {
        discard;
    }

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
