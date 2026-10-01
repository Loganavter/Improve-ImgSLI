#version 440

// Engine slot-array vertex shader (engine.gpu.array_draw SLOT_INSTANCE_*).
//
// Per-instance transform: iPanFit (pan xy + fit zw), iZoom, iTileRect,
// iSlotRect. One instanced draw covers N independent slots (Multi Compare)
// or one full-canvas slot (Quick Look). aTexCoord's 0/1 corner selector
// picks a corner of this instance's screen-space bounding box (iBBox)
// instead of the whole framebuffer, so the fragment shader runs over a
// triangle sized to the tile's real footprint.

layout(location = 0) in vec2 aPos;
layout(location = 1) in vec2 aTexCoord;

// Per-instance (shared engine slot layout).
layout(location = 2) in vec4 iPanFit;      // xy = pan offset, zw = fit scale
layout(location = 3) in float iZoom;
layout(location = 4) in vec4 iTileRect;
layout(location = 5) in vec4 iSlotRect;
layout(location = 6) in vec2 iContentScale; // contentPx / arrayLayerPx
layout(location = 7) in int iLayer;
layout(location = 8) in vec4 iBBox;

layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;
    vec4 letterbox;
};

layout(location = 0) out vec2 TexCoord;
layout(location = 1) out vec4 vPanFit;
layout(location = 2) out float vZoom;
layout(location = 3) out vec4 vTileRect;
layout(location = 4) out vec4 vSlotRect;
layout(location = 5) out vec2 vContentScale;
layout(location = 6) flat out int vLayer;

void main()
{
    vec2 targetUV = iBBox.xy + aTexCoord * iBBox.zw;
    vec2 position = vec2(targetUV.x * 2.0 - 1.0, 1.0 - targetUV.y * 2.0);
    gl_Position = mvp * vec4(position, 0.0, 1.0);
    TexCoord = targetUV;
    vPanFit = iPanFit;
    vZoom = iZoom;
    vTileRect = iTileRect;
    vSlotRect = iSlotRect;
    vContentScale = iContentScale;
    vLayer = iLayer;
}
