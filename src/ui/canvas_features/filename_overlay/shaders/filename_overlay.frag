#version 440

layout(binding = 1) uniform sampler2D uTex;

layout(location = 0) in vec2 vTexCoord;
layout(location = 0) out vec4 fragColor;

void main()
{
    fragColor = texture(uTex, vTexCoord);
}
