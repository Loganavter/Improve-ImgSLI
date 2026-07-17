#version 440

layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;
    vec2 resolution;
    float positionPx;
    float halfThicknessPx;
    vec4 color;
    // Widget-px AABB of the letterbox *after* zoom/pan. Discard outside so the
    // line tracks the image without QRhi scissor Y-flip (live canvas and
    // magnifier disagree on content scissor; see DividerPass).
    vec4 clipRectPx;
    int isHorizontal;
};

layout(location = 0) in vec2 vTexCoord;
layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 fragPx = vTexCoord * resolution;
    if (fragPx.x < clipRectPx.x || fragPx.y < clipRectPx.y
        || fragPx.x > clipRectPx.x + clipRectPx.z
        || fragPx.y > clipRectPx.y + clipRectPx.w)
        discard;
    float coord = isHorizontal != 0 ? fragPx.y : fragPx.x;
    if (abs(coord - positionPx) > max(0.5, halfThicknessPx))
        discard;
    fragColor = color;
}
