#version 440

layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;
};

layout(location = 0) in vec2 aPos;
layout(location = 1) in vec2 aUV;

layout(location = 0) out vec2 vTexCoord;

void main()
{
    gl_Position = mvp * vec4(aPos, 0.0, 1.0);
    vTexCoord = aUV;
}
