#version 440

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
    vec4 tileRect1;
    vec4 tileRect2;
    // Expanding-canvas frame in widget UV + fill for pads inside it
    // (video uncrop / export). zw==0 disables; fill.a==0 → transparent.
    vec4 canvasLetterbox;
    vec4 letterboxFill;
};

layout(binding = 1) uniform sampler2D image1;
layout(binding = 2) uniform sampler2D image2;
layout(binding = 3) uniform sampler2D imageDiff;

layout(location = 0) in vec2 vTexCoord;
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

vec4 sampleImage(sampler2D tex, vec2 uv)
{
    return applyChannel(texture(tex, uv), channelMode);
}

vec4 computeEdge(sampler2D tex, vec2 uv)
{
    vec2 stepPx = 1.0 / vec2(textureSize(tex, 0));
    float tl = luminance(sampleImage(tex, uv + vec2(-stepPx.x, -stepPx.y)).rgb);
    float t  = luminance(sampleImage(tex, uv + vec2(0.0, -stepPx.y)).rgb);
    float tr = luminance(sampleImage(tex, uv + vec2(stepPx.x, -stepPx.y)).rgb);
    float l  = luminance(sampleImage(tex, uv + vec2(-stepPx.x, 0.0)).rgb);
    float r  = luminance(sampleImage(tex, uv + vec2(stepPx.x, 0.0)).rgb);
    float bl = luminance(sampleImage(tex, uv + vec2(-stepPx.x, stepPx.y)).rgb);
    float b  = luminance(sampleImage(tex, uv + vec2(0.0, stepPx.y)).rgb);
    float br = luminance(sampleImage(tex, uv + vec2(stepPx.x, stepPx.y)).rgb);
    float gx = -tl - 2.0 * l - bl + tr + 2.0 * r + br;
    float gy = -tl - 2.0 * t - tr + bl + 2.0 * b + br;
    float edge = smoothstep(0.05, 0.3, sqrt(gx * gx + gy * gy));
    return vec4(edge, edge, edge, 1.0);
}

void main()
{
    vec2 center = vec2(0.5);
    // zoom is per-axis (docs/dev/TILED_RENDERING_DESIGN.md Phase 3): live
    // interactive/preserve-zoom rendering always sets zoom.x == zoom.y
    // (isotropic), but tiled export needs an anisotropic crop window when a
    // tile's aspect ratio differs from the canvas's.
    vec2 uv = (vTexCoord - center) / zoom + center - offset;
    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
        fragColor = vec4(0.0);
        return;
    }

    // Content-space spit (same model as magnifier ``internalSplit``): compare
    // against the letterboxed image UV, not screen ``vTexCoord``. ``splitPosition``
    // is store ``split_position_visual`` in ``[0,1]`` — pan/zoom must not be
    // baked into this uniform. Screen-space display spit is only for DividerPass.
    vec2 splitUV = (uv - letterbox1.xy) / letterbox1.zw;
    bool useFirst = (isHorizontal != 0 ? splitUV.y : splitUV.x) < splitPosition;
    vec4 letterbox = useFirst ? letterbox1 : letterbox2;
    vec2 sampleUV = (uv - letterbox.xy) / letterbox.zw;
    if (sampleUV.x < 0.0 || sampleUV.x > 1.0 || sampleUV.y < 0.0 || sampleUV.y > 1.0) {
        // Inside the padded canvas frame but outside the image → fill color.
        // Outside the canvas frame → transparent (theme chrome shows through).
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

    // Phase 1 tiling (docs/dev/TILED_RENDERING_DESIGN.md): image1/image2
    // sample from whichever GPU tile the current draw call bound, not
    // necessarily the whole image. tileRect1/2 is that tile's rect in
    // per-side normalized-image space; a fragment only lights up on the
    // one draw call (of the N1*N2 issued this frame) whose tile actually
    // covers it — out-of-tile fragments contribute nothing under the
    // existing SrcAlpha/OneMinusSrcAlpha blend, same pattern as the uv/
    // sampleUV bounds checks above. N=1 (tileRect == (0,0,1,1)) makes
    // tileUV == sampleUV, unchanged from pre-tiling behavior. imageDiff
    // (diffMode == 4) is not tiled yet — Phase 4 scope.
    vec2 tileUV1 = (sampleUV - tileRect1.xy) / tileRect1.zw;
    vec2 tileUV2 = (sampleUV - tileRect2.xy) / tileRect2.zw;
    if (diffMode != 4) {
        bool inTile1 = tileUV1.x >= 0.0 && tileUV1.x <= 1.0 && tileUV1.y >= 0.0 && tileUV1.y <= 1.0;
        bool inTile2 = tileUV2.x >= 0.0 && tileUV2.x <= 1.0 && tileUV2.y >= 0.0 && tileUV2.y <= 1.0;
        if (!inTile1 || !inTile2) {
            fragColor = vec4(0.0);
            return;
        }
    }

    vec4 color1 = sampleImage(image1, tileUV1);
    vec4 color2 = sampleImage(image2, tileUV2);

    if (diffMode == 1) {
        vec3 diff = abs(color1.rgb - color2.rgb);
        float maxDiff = max(diff.r, max(diff.g, diff.b));
        fragColor = maxDiff > diffThreshold ? vec4(1.0, 0.35, 0.47, 1.0) : color1;
    } else if (diffMode == 2) {
        vec3 diff = abs(color1.rgb - color2.rgb);
        float gray = clamp(luminance(diff) * 4.0, 0.0, 1.0);
        fragColor = vec4(gray, gray, gray, 1.0);
    } else if (diffMode == 3) {
        fragColor = useFirst ? computeEdge(image1, tileUV1) : computeEdge(image2, tileUV2);
    } else if (diffMode == 4 && diffSourceReady != 0) {
        fragColor = applyChannel(texture(imageDiff, sampleUV), channelMode);
    } else {
        fragColor = useFirst ? color1 : color2;
    }
}
