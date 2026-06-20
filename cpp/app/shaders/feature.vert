#version 440

layout(location = 0) in vec2 position;
layout(location = 1) in vec2 texcoord;
layout(location = 0) out vec2 uv;

layout(std140, binding = 0) uniform Feature {
    mat4 clipSpaceCorrection;
    vec4 viewport;
    vec4 params0;
    vec4 params1;
    vec4 params2;
    vec4 color;
} uniforms;

void main()
{
    uv = texcoord;
    gl_Position = uniforms.clipSpaceCorrection * vec4(position, 0.0, 1.0);
}
