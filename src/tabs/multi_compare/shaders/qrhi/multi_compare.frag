#version 440

layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;
    vec2 panOffset;
    vec2 fitScale;
    float zoom;
    float _pad0;
    float _pad1;
    float _pad2;
};

layout(binding = 1) uniform sampler2D image;

layout(location = 0) in vec2 TexCoord;
layout(location = 0) out vec4 FragColor;

void main()
{
    vec2 uv = (TexCoord - vec2(0.5)) / fitScale + vec2(0.5);
    uv = (uv - vec2(0.5)) / zoom + vec2(0.5) - panOffset;
    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
        FragColor = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }
    FragColor = texture(image, uv);
}
