#version 440

// Multi-tile/multi-slot counterpart to multi_compare.vert (docs/dev/
// rendering/tile-array-atlas-plan.md Phase 4): one instanced draw replaces
// N per-tile draw calls across every visible layer/slot combined -- unlike
// image_compare's array path (Phase 2), there is no cross-image pairing
// here, so each instance is exactly one (layer, tile) pair. Per-instance
// data carries what used to be one tile draw's own uniform block
// (pan/fit/zoom, tileRect, slotRect) plus which texture-array layer to
// sample.
//
// Phase 10 port (overdraw fix, mirrors image_compare's base_array.vert):
// position/texCoord are no longer a shared fullscreen quad emitted
// unclipped by every instance. Each instance carries its own screen-space
// bounding box (iBBox -- this tile's on-screen footprint, computed
// CPU-side in base_images.py's ``_instance_bbox`` by inverting
// multi_compare_array.frag's letterbox->slotRect->fit/zoom/pan->tileRect
// chain, since that chain is exactly what the frag shader's own discards
// would otherwise let through for this instance anyway). aTexCoord's 0/1
// corner selector picks a corner of iBBox instead of the full [0,1]
// screen, so TexCoord's meaning is unchanged and the fragment shader needs
// no changes -- it just now runs over a triangle sized to the instance's
// real footprint instead of the whole framebuffer. Unlike image_compare,
// no instance needs to be forced back to a full-screen bbox: this shader
// has no background/pillarbox fill path that depends on always having some
// instance cover the whole canvas (base_array.frag's canvasLetterbox
// counterpart doesn't exist here -- every pixel outside every tile's own
// footprint is simply discarded to transparent).

layout(location = 0) in vec2 aPos;
layout(location = 1) in vec2 aTexCoord;

// Per-instance.
layout(location = 2) in vec4 iPanFit;      // xy = pan offset, zw = fit scale
layout(location = 3) in float iZoom;
layout(location = 4) in vec4 iTileRect;
layout(location = 5) in vec4 iSlotRect;
layout(location = 6) in vec2 iContentScale; // contentPx / arrayLayerPx
layout(location = 7) in int iLayer;
// Screen-space (xy = origin, zw = size) bounding box this instance's
// geometry is clipped to -- see file header comment.
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
