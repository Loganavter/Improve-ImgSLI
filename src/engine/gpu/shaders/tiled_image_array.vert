#version 440

// Engine single-image tiled-array vertex shader (engine.gpu.tiled_image_view).
//
// One instance per visible tile of the source's texture-array grid (shared
// per-instance layout, engine.gpu.array_draw locations 2..8). There is no
// pairing: the instance's screen-space bounding box (iBBox) is the tile's own
// footprint under the letterbox -> contain-fit -> zoom -> pan chain.
// aTexCoord's 0/1 corner selector picks a corner of iBBox instead of the whole
// canvas, so the fragment shader runs over a triangle sized to this tile's
// real footprint.

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

// mat4 mvp(64) + vec4 letterbox(16) + vec2 pan(8) + vec2 zoom(8) + vec2
// fit(8) + vec2 _pad(8); extra bytes reserved after (unused here).
layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;
    vec4 letterbox;
    vec2 pan;
    vec2 zoom;
    vec2 fit;
    vec2 _pad;
};

layout(location = 0) out vec2 vTexCoord;
layout(location = 1) out vec4 vRect;
layout(location = 2) out vec2 vContentScale;
layout(location = 3) flat out int vLayer;

void main()
{
    vec2 targetUV = iBBox.xy + aTexCoord * iBBox.zw;
    vec2 position = vec2(targetUV.x * 2.0 - 1.0, 1.0 - targetUV.y * 2.0);
    gl_Position = mvp * vec4(position, 0.0, 1.0);
    vTexCoord = targetUV;
    vRect = iRect1;
    vContentScale = iContentScale.xy;
    vLayer = iLayers.x;
}
