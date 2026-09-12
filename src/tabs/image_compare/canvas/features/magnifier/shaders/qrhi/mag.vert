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

layout(location = 0) in vec2 aPos;
layout(location = 1) in vec2 aTexCoord;

layout(location = 0) out vec2 TexCoord;

void main()
{
    float x = mix(quadBounds.x, quadBounds.z, aTexCoord.x);
    float y = mix(quadBounds.y, quadBounds.w, 1.0 - aTexCoord.y);
    // Scale around the disk's own NDC center, not the viewport origin --
    // quadBounds.x/z and .y/.w already place the un-zoomed disk at its
    // correct screen position (see MagnifierPass.prepare's content_x0..y1,
    // computed straight from cx_px/cy_px in widget-px, same as the border
    // pass -- pack_border_disk_uniform's center_x/center_y are the same raw
    // widget-px, radius scaled by zoom the same way). No magPan translation:
    // border_disk (the ring drawn around this same disk) never applies pan
    // either, so panning only this content would make it visibly detach
    // from its own border ring by however far the canvas has been panned.
    // magPan is kept in the UBuf layout only so struct packing stays
    // unchanged for other passes reusing this shader's layout.
    float centerX = (quadBounds.x + quadBounds.z) * 0.5;
    float centerY = (quadBounds.y + quadBounds.w) * 0.5;
    x = centerX + (x - centerX) * magZoom;
    y = centerY + (y - centerY) * magZoom;
    gl_Position = mvp * vec4(x, y, 0.0, 1.0);
    TexCoord = aTexCoord;
}
