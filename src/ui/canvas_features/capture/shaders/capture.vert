#version 440

layout(location = 0) in vec2 position;
layout(location = 1) in vec2 texCoord;

layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;
    vec2 resolution;
    vec2 centerPx;
    float radiusPx;
    float lineWidthPx;
    vec4 color;
};

layout(location = 0) out vec2 vTexCoord;

void main()
{
    gl_Position = mvp * vec4(position, 0.0, 1.0);
    vTexCoord = texCoord;
}
