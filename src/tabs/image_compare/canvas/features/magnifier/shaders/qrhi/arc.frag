#version 440

layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;
    vec2 resolution;
    vec2 center_px;
    float radius_px;
    float lineWidth_px;
    float startAngleDeg;
    float spanAngleDeg;
    vec4 color;
};

layout(location = 0) in vec2 TexCoord;
layout(location = 0) out vec4 FragColor;

void main()
{
    vec2 frag_px = TexCoord * resolution;
    float dist   = distance(frag_px, center_px);
    float half_w = max(0.5, lineWidth_px * 0.5);
    float aa     = 1.15;
    float delta  = abs(dist - radius_px);
    float solid_w = max(0.0, half_w - aa);
    float ring   = 1.0 - smoothstep(solid_w, half_w + aa, delta);
    if (ring <= 0.01) discard;
    float angle_deg = degrees(atan(-(frag_px.y - center_px.y), frag_px.x - center_px.x));
    if (angle_deg < 0.0) angle_deg += 360.0;
    bool in_arc;
    if (abs(spanAngleDeg) >= 359.9) {
        in_arc = true;
    } else {
        float sa = mod(startAngleDeg, 360.0);
        if (sa < 0.0) sa += 360.0;
        float ea = mod(startAngleDeg + spanAngleDeg, 360.0);
        if (ea < 0.0) ea += 360.0;
        if (sa <= ea) {
            in_arc = (angle_deg >= sa && angle_deg <= ea);
        } else {
            in_arc = (angle_deg >= sa || angle_deg <= ea);
        }
    }
    if (!in_arc) discard;
    float sa2 = mod(startAngleDeg, 360.0);
    if (sa2 < 0.0) sa2 += 360.0;
    float angle_from_start = mod(angle_deg - sa2 + 360.0, 360.0);
    float arc_len_px = angle_from_start * 3.14159265 / 180.0 * radius_px;
    float dash_cycle = 12.0;
    if (mod(arc_len_px, dash_cycle) > 8.0) discard;
    FragColor = vec4(color.rgb, color.a * ring);
}
