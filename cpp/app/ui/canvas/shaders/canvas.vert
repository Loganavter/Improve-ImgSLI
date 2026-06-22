#version 440

layout(location = 0) in vec2 position;
layout(location = 1) in vec2 texcoord;
layout(location = 0) out vec2 uv;

layout(std140, binding = 0) uniform Vert {
    mat4 clipSpaceCorrection;
    vec4 params;
} uniforms;

void main()
{
    uv = texcoord;
    gl_Position = uniforms.clipSpaceCorrection * vec4(position, 0.0, 1.0);
}
