#version 440

// Quick Look single-source tiled-array vertex shader (task-ql-tiles-w1).
//
// One instance per visible tile of the full TiledPixelStore's texture-array
// grid (engine.gpu.array_draw per-instance layout, locations 2..8). Unlike
// the compare tabs there is no pairing/letterbox: the single slot covers the
// whole framebuffer, so the instance's screen-space bounding box (iBBox) is
// the tile's own footprint under the QL contain-fit + zoom + pan chain.
// aTexCoord's 0/1 corner selector picks a corner of iBBox instead of the
// whole canvas, so the fragment shader runs over a triangle sized to this
// tile's real footprint.

layout(location = 0) in vec2 aPos;
layout(location = 1) in vec2 aTexCoord;

// Per-instance (shared engine layout).
layout(location = 2) in vec4 iRect1;
layout(location = 3) in vec4 iRect2;
layout(location = 4) in vec4 iContentScale;
layout(location = 5) in vec2 iContentScaleDiff;
layout(location = 6) in ivec3 iLayers;
layout(location = 7) in vec4 iBBox;
layout(location = 8) in vec4 iRectDiff;

// Quick Look uniform block: clip matrix + the single-slot fit/zoom/pan chain
// (see preview_zoom.py). std140: 64 + 8 + 8 + 8 = 88, padded to 96.
layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;
    vec2 pan;
    vec2 zoom;
    vec2 fit;
    vec2 _pad;
};

layout(location = 0) out vec2 vTexCoord;
layout(location = 1) out vec4 vRect1;
layout(location = 2) out vec2 vContentScale;
layout(location = 3) flat out int vLayer;

void main()
{
    vec2 targetUV = iBBox.xy + aTexCoord * iBBox.zw;
    vec2 position = vec2(targetUV.x * 2.0 - 1.0, 1.0 - targetUV.y * 2.0);
    gl_Position = mvp * vec4(position, 0.0, 1.0);
    vTexCoord = targetUV;
    vRect1 = iRect1;
    vContentScale = iContentScale.xy;
    vLayer = iLayers.x;
}
