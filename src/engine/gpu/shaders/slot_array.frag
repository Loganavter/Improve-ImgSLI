#version 440

// Engine slot-array fragment shader (engine.gpu.array_draw SLOT_INSTANCE_*).
//
// Per-pixel chain: letterbox -> slotRect -> fit/zoom/pan -> tileRect.
// Tile content is uploaded 1:1 into the top-left corner of a fixed-size
// array layer, so contentScale only rescales the UV used to address it.

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
    // Micro-seam tolerance: adjacent tile rects share an edge at 0/1 in
    // tileUV; float rounding can make both sides compute a hair outside
    // [0,1] and both discard (a transparent grid seam). Expand by 1e-3 so
    // the apron overlap always covers the boundary (matches image_compare).
    if (tileUV.x < -0.001 || tileUV.x > 1.001 || tileUV.y < -0.001 || tileUV.y > 1.001) {
        FragColor = vec4(0.0);
        return;
    }

    vec2 arrUV = tileUV * vContentScale;
    FragColor = texture(tileArray, vec3(arrUV, float(vLayer)));
}
