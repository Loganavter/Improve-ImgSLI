#version 440

// Multi-tile counterpart to base.frag (docs/dev/rendering/
// tile-array-atlas-plan.md Phase 2). Per-pixel comparison logic
// (split/diff/channel) is identical to base.frag; the only difference is
// that image1/image2/imageDiff are layers of one shared texture array
// (sampler2DArray) instead of three separate whole-texture sampler2D
// bindings, addressed by this instance's iLayers. Tile content is
// uploaded 1:1 (no resampling) into the top-left corner of a
// fixed-size array layer (see resources.py's _ARRAY_LAYER_PX), so
// texel-space math (computeEdge's step size, mip selection) is
// unaffected by content-scale -- content-scale only rescales the UV
// used to *address* that corner.

layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;
    vec2 offset;
    vec2 zoom;
    float splitPosition;
    vec4 letterbox1;
    vec4 letterbox2;
    int isHorizontal;
    int channelMode;
    int diffMode;
    int diffSourceReady;
    float diffThreshold;
    vec4 canvasLetterbox;
    vec4 letterboxFill;
};

layout(binding = 1) uniform sampler2DArray tileArray;

layout(location = 0) in vec2 vTexCoord;
layout(location = 1) in vec4 vRect1;
layout(location = 2) in vec4 vRect2;
layout(location = 3) in vec4 vContentScale;
layout(location = 4) in vec2 vContentScaleDiff;
layout(location = 5) flat in ivec3 vLayers;
layout(location = 6) in vec4 vRectDiff;

layout(location = 0) out vec4 fragColor;

vec4 applyChannel(vec4 color, int mode)
{
    if (mode == 1) return vec4(color.r, 0.0, 0.0, color.a);
    if (mode == 2) return vec4(0.0, color.g, 0.0, color.a);
    if (mode == 3) return vec4(0.0, 0.0, color.b, color.a);
    if (mode == 4) {
        float luma = dot(color.rgb, vec3(0.299, 0.587, 0.114));
        return vec4(luma, luma, luma, color.a);
    }
    return color;
}

float luminance(vec3 color)
{
    return dot(color, vec3(0.299, 0.587, 0.114));
}

vec4 sampleArray(int layer, vec2 uv)
{
    return applyChannel(texture(tileArray, vec3(uv, float(layer))), channelMode);
}

vec4 computeEdgeArray(int layer, vec2 uv)
{
    vec2 stepPx = 1.0 / vec2(textureSize(tileArray, 0).xy);
    float tl = luminance(sampleArray(layer, uv + vec2(-stepPx.x, -stepPx.y)).rgb);
    float t  = luminance(sampleArray(layer, uv + vec2(0.0, -stepPx.y)).rgb);
    float tr = luminance(sampleArray(layer, uv + vec2(stepPx.x, -stepPx.y)).rgb);
    float l  = luminance(sampleArray(layer, uv + vec2(-stepPx.x, 0.0)).rgb);
    float r  = luminance(sampleArray(layer, uv + vec2(stepPx.x, 0.0)).rgb);
    float bl = luminance(sampleArray(layer, uv + vec2(-stepPx.x, stepPx.y)).rgb);
    float b  = luminance(sampleArray(layer, uv + vec2(0.0, stepPx.y)).rgb);
    float br = luminance(sampleArray(layer, uv + vec2(stepPx.x, stepPx.y)).rgb);
    float gx = -tl - 2.0 * l - bl + tr + 2.0 * r + br;
    float gy = -tl - 2.0 * t - tr + bl + 2.0 * b + br;
    float edge = smoothstep(0.05, 0.3, sqrt(gx * gx + gy * gy));
    return vec4(edge, edge, edge, 1.0);
}

void main()
{
    vec2 center = vec2(0.5);
    vec2 uv = (vTexCoord - center) / zoom + center - offset;
    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
        fragColor = vec4(0.0);
        return;
    }

    vec2 splitUV = (uv - letterbox1.xy) / letterbox1.zw;
    bool useFirst = (isHorizontal != 0 ? splitUV.y : splitUV.x) < splitPosition;
    vec4 letterbox = useFirst ? letterbox1 : letterbox2;
    vec2 sampleUV = (uv - letterbox.xy) / letterbox.zw;
    if (sampleUV.x < 0.0 || sampleUV.x > 1.0 || sampleUV.y < 0.0 || sampleUV.y > 1.0) {
        if (canvasLetterbox.z > 0.0 && canvasLetterbox.w > 0.0 && letterboxFill.a > 0.0) {
            vec2 canvasUV = (uv - canvasLetterbox.xy) / canvasLetterbox.zw;
            if (canvasUV.x >= 0.0 && canvasUV.x <= 1.0 && canvasUV.y >= 0.0 && canvasUV.y <= 1.0) {
                fragColor = letterboxFill;
                return;
            }
        }
        fragColor = vec4(0.0);
        return;
    }

    vec2 tileUV1 = (sampleUV - vRect1.xy) / vRect1.zw;
    vec2 tileUV2 = (sampleUV - vRect2.xy) / vRect2.zw;
    if (diffMode != 4) {
        bool inTile1 = tileUV1.x >= 0.0 && tileUV1.x <= 1.0 && tileUV1.y >= 0.0 && tileUV1.y <= 1.0;
        bool inTile2 = tileUV2.x >= 0.0 && tileUV2.x <= 1.0 && tileUV2.y >= 0.0 && tileUV2.y <= 1.0;
        if (!inTile1 || !inTile2) {
            fragColor = vec4(0.0);
            return;
        }
    }

    vec2 arrUV1 = tileUV1 * vContentScale.xy;
    vec2 arrUV2 = tileUV2 * vContentScale.zw;

    vec4 color1 = sampleArray(vLayers.x, arrUV1);
    vec4 color2 = sampleArray(vLayers.y, arrUV2);

    if (diffMode == 1) {
        vec3 diff = abs(color1.rgb - color2.rgb);
        float maxDiff = max(diff.r, max(diff.g, diff.b));
        fragColor = maxDiff > diffThreshold ? vec4(1.0, 0.35, 0.47, 1.0) : color1;
    } else if (diffMode == 2) {
        vec3 diff = abs(color1.rgb - color2.rgb);
        float gray = clamp(luminance(diff) * 4.0, 0.0, 1.0);
        fragColor = vec4(gray, gray, gray, 1.0);
    } else if (diffMode == 3) {
        fragColor = useFirst ? computeEdgeArray(vLayers.x, arrUV1) : computeEdgeArray(vLayers.y, arrUV2);
    } else if (diffMode == 4 && diffSourceReady != 0) {
        // vRectDiff = (0,0,1,1) (identity) when diff isn't split into
        // multiple tiles, so this reduces to the old `sampleUV *
        // vContentScaleDiff` exactly. Clamp rather than discard at the
        // tile's own edge: this instance's on-screen footprint is already
        // clipped to its assigned diff tile via iBBox, so any out-of-[0,1]
        // here is float rounding at that boundary, not a real sampling
        // error -- clamping avoids a seam a discard would leave.
        vec2 tileUVDiff = clamp((sampleUV - vRectDiff.xy) / vRectDiff.zw, 0.0, 1.0);
        vec2 arrUVDiff = tileUVDiff * vContentScaleDiff;
        fragColor = sampleArray(vLayers.z, arrUVDiff);
    } else {
        fragColor = useFirst ? color1 : color2;
    }
}
