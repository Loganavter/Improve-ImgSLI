#version 440

// Multi-tile/multi-slot counterpart to multi_compare.frag (docs/dev/
// rendering/tile-array-atlas-plan.md Phase 4). Per-pixel projection math
// (letterbox -> slotRect -> fit/zoom/pan -> tileRect) is identical to
// multi_compare.frag; the only difference is that the source image is one
// layer of a shared texture array (sampler2DArray) instead of its own whole
// sampler2D, addressed by this instance's iLayer. Tile content is uploaded
// 1:1 (no resampling) into the top-left corner of a fixed-size array layer
// (see base_images.py's _ARRAY_LAYER_PX) -- contentScale only rescales the
// UV used to *address* that corner, it never resamples the content itself.

layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;
    vec4 letterbox;
};

layout(binding = 1) uniform sampler2DArray tileArray;

layout(location = 0) in vec2 TexCoord;
layout(location = 1) in vec4 vPanFit;
layout(location = 2) in float vZoom;
layout(location = 3) in vec4 vTileRect;
layout(location = 4) in vec4 vSlotRect;
layout(location = 5) in vec2 vContentScale;
layout(location = 6) flat in int vLayer;

layout(location = 0) out vec4 FragColor;

void main()
{
    if (letterbox.z <= 0.0 || letterbox.w <= 0.0) {
        FragColor = vec4(0.0);
        return;
    }
    vec2 contentUV = (TexCoord - letterbox.xy) / letterbox.zw;
    if (contentUV.x < 0.0 || contentUV.x > 1.0 || contentUV.y < 0.0 || contentUV.y > 1.0) {
        FragColor = vec4(0.0);
        return;
    }

    if (vSlotRect.z <= 0.0 || vSlotRect.w <= 0.0) {
        FragColor = vec4(0.0);
        return;
    }
    vec2 slotUV = (contentUV - vSlotRect.xy) / vSlotRect.zw;
    if (slotUV.x < 0.0 || slotUV.x > 1.0 || slotUV.y < 0.0 || slotUV.y > 1.0) {
        FragColor = vec4(0.0);
        return;
    }

    vec2 uv = (slotUV - vec2(0.5)) / vPanFit.zw + vec2(0.5);
    uv = (uv - vec2(0.5)) / vZoom + vec2(0.5) - vPanFit.xy;
    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
        FragColor = vec4(0.0);
        return;
    }

    vec2 tileUV = (uv - vTileRect.xy) / vTileRect.zw;
    if (tileUV.x < 0.0 || tileUV.x > 1.0 || tileUV.y < 0.0 || tileUV.y > 1.0) {
        FragColor = vec4(0.0);
        return;
    }

    vec2 arrUV = tileUV * vContentScale;
    FragColor = texture(tileArray, vec3(arrUV, float(vLayer)));
}
