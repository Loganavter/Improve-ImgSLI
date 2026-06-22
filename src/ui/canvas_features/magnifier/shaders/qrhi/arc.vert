#version 440

layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;
    vec2 resolution;
    vec2 center_px;
    float radius_px;
    float lineWidth_px;
    float startAngleDeg;
    float spanAngleDeg;
    vec4 color;
};

layout(location = 0) in vec2 aPos;
layout(location = 1) in vec2 aTexCoord;

layout(location = 0) out vec2 TexCoord;

void main()
{
    gl_Position = mvp * vec4(aPos, 0.0, 1.0);
    TexCoord = aTexCoord;
}
