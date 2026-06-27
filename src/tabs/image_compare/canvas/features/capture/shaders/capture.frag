#version 440

layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;
    vec2 resolution;
    vec2 centerPx;
    float radiusPx;
    float lineWidthPx;
    vec4 color;
};

layout(location = 0) in vec2 vTexCoord;
layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 fragPx = vTexCoord * resolution;
    float delta = abs(distance(fragPx, centerPx) - radiusPx);
    float halfWidth = max(0.5, lineWidthPx * 0.5);
    float ring = 1.0 - smoothstep(
        max(0.0, halfWidth - 1.15),
        halfWidth + 1.15,
        delta
    );
    if (ring <= 0.01) discard;
    fragColor = vec4(color.rgb, color.a * ring);
}
