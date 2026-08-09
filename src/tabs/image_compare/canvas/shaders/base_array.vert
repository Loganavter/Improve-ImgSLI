#version 440

// Multi-tile counterpart to base.vert (docs/dev/rendering/
// tile-array-atlas-plan.md Phase 2). One instanced draw replaces N
// per-tile-pair draw calls; per-instance data carries what used to be a
// whole draw call's own uniform slot (tileRect1/2 + which texture-array
// layer each side samples).
//
// Phase 10 (overdraw fix): position/texCoord are no longer a shared
// fullscreen quad emitted unclipped by every instance. Each instance now
// carries its own content-space bounding box (iBBox -- rect1's and rect2's
// on-screen footprints intersected, computed CPU-side in
// build_array_draw_plan/_intersection_rect since that's the only region
// base_array.frag's tileUV1/tileUV2 discard could ever let through for
// this instance anyway). texCoord's 0/1 corner selector picks a corner of
// iBBox instead of the full [0,1] canvas, and the result is mapped back
// through the inverse of base_array.frag's ``uv = (vTexCoord - center) /
// zoom + center - offset`` to get the screen-space vTexCoord/gl_Position
// that would have produced that content-space corner -- so vTexCoord's
// meaning is unchanged and base_array.frag needs no changes at all, it
// just now runs over a triangle sized to the instance's real footprint
// instead of the whole framebuffer. One instance is always given
// iBBox = (0,0,1,1) by the caller (render()) regardless of its actual
// footprint, to guarantee at least one instance still covers
// canvasLetterbox/letterboxFill's pillarbox background-fill area, which
// depends only on uniforms (not on any instance's own tile rect) and so is
// painted correctly by any fullscreen instance.

layout(location = 0) in vec2 position;
layout(location = 1) in vec2 texCoord;

// Per-instance.
layout(location = 2) in vec4 iRect1;
layout(location = 3) in vec4 iRect2;
// xy = image1 content-scale (contentPx / arrayLayerPx), zw = image2's.
layout(location = 4) in vec4 iContentScale;
layout(location = 5) in vec2 iContentScaleDiff;
// x = layer1, y = layer2, z = layerDiff (unused unless diffMode == 4).
layout(location = 6) in ivec3 iLayers;
// Content-space (xy = origin, zw = size) bounding box this instance's
// geometry is clipped to -- see file header comment.
layout(location = 7) in vec4 iBBox;
// The diff/SSIM tile this instance samples, in the same content-space as
// iRect1/iRect2 (xy = origin, zw = size) -- identity (0,0,1,1) when diff
// isn't split into multiple tiles, matching the old direct-sampleUV
// behavior exactly. Needed because a diff source can have its own tile
// grid finer than iBBox's (build_array_draw_plan splits one draw instance
// per overlapping diff tile): without subtracting this tile's own origin
// first, base_array.frag sampled every diff-tile instance with the same
// whole-canvas UV regardless of which tile it was assigned, showing each
// tile's content at the wrong, effectively-random offset within itself
// (docs/dev/rendering/qrhi-gotchas.md #ssim-diff-blocky-mosaic-at-coarse-lod).
layout(location = 8) in vec4 iRectDiff;

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

layout(location = 0) out vec2 vTexCoord;
layout(location = 1) out vec4 vRect1;
layout(location = 2) out vec4 vRect2;
layout(location = 3) out vec4 vContentScale;
layout(location = 4) out vec2 vContentScaleDiff;
layout(location = 5) flat out ivec3 vLayers;
layout(location = 6) out vec4 vRectDiff;

void main()
{
    vec2 center = vec2(0.5);
    vec2 targetUV = iBBox.xy + texCoord * iBBox.zw;
    vec2 screenUV = (targetUV - center + offset) * zoom + center;
    vec2 position2 = vec2(screenUV.x * 2.0 - 1.0, 1.0 - screenUV.y * 2.0);
    gl_Position = mvp * vec4(position2, 0.0, 1.0);
    vTexCoord = screenUV;
    vRect1 = iRect1;
    vRect2 = iRect2;
    vContentScale = iContentScale;
    vContentScaleDiff = iContentScaleDiff;
    vLayers = iLayers;
    vRectDiff = iRectDiff;
}
