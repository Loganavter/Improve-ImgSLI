#version 440

layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;
    vec2 resolution;
    vec2 center_px;
    float radius_px;
    float borderWidth_px;
    vec4 color;
};

layout(location = 0) in vec2 TexCoord;
layout(location = 0) out vec4 FragColor;

void main()
{
    vec2 frag_px = TexCoord * resolution;
    float dist = distance(frag_px, center_px);
    float aa = 1.15;
    float outer_alpha = 1.0 - smoothstep(max(0.0, radius_px - aa), radius_px + aa, dist);
    float inner_radius = max(0.0, radius_px - borderWidth_px);
    float inner_alpha = smoothstep(max(0.0, inner_radius - aa), inner_radius + aa, dist);
    float alpha = outer_alpha * inner_alpha;
    if (alpha <= 0.01) discard;
    FragColor = vec4(color.rgb, color.a * alpha);
}
