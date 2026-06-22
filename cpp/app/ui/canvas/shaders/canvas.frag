#version 440

layout(location = 0) in vec2 uv;
layout(location = 0) out vec4 fragColor;

layout(binding = 1) uniform sampler2D imageTexture;
layout(binding = 2) uniform sampler2D imageTexture2;

layout(std140, binding = 0) uniform Canvas {
    mat4 clipSpaceCorrection;
    vec4 params;
} uniforms;

void main()
{
    bool horizontal = uniforms.params.y > 0.5;
    float coordinate = horizontal ? uv.y : uv.x;
    fragColor = coordinate <= uniforms.params.x
        ? texture(imageTexture, uv)
        : texture(imageTexture2, uv);
}
