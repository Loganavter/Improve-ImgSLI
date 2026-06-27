#version 440

layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;
    vec2 resolution;
    float positionPx;
    float halfThicknessPx;
    vec4 color;
    int isHorizontal;
};

layout(location = 0) in vec2 vTexCoord;
layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 fragPx = vTexCoord * resolution;
    float coord = isHorizontal != 0 ? fragPx.y : fragPx.x;
    if (abs(coord - positionPx) > max(0.5, halfThicknessPx))
        discard;
    fragColor = color;
}
