#version 440

layout(binding = 1) uniform sampler2D overlayTex;

layout(location = 0) in vec2 TexCoord;
layout(location = 0) out vec4 FragColor;

void main()
{
    FragColor = texture(overlayTex, TexCoord);
}
