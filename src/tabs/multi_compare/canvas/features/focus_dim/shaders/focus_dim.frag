#version 440

layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;
    // Focus-dim bar as pre-clip NDC bounds (x0, y0, x1, y1); the fragment
    // shader discards everything outside, so one fullscreen-quad draw per
    // bar paints exactly the old raster bar coverage.
    vec4 rectNdc;
    vec4 color;
};

layout(location = 0) in vec2 vTexCoord;
layout(location = 0) out vec4 fragColor;

void main()
{
    // Fullscreen-quad texcoord (0,0) rides the top-left corner (-1,+1) and
    // (1,1) the bottom-right one (see engine.overlay.FULLSCREEN_VERTICES),
    // so this NDC reconstruction is backend-independent: the clip-space
    // correction matrix applies identically to the old NDC vertex quads.
    vec2 ndc = vec2(vTexCoord.x * 2.0 - 1.0, 1.0 - vTexCoord.y * 2.0);
    if (ndc.x < rectNdc.x || ndc.y < rectNdc.y
        || ndc.x > rectNdc.z || ndc.y > rectNdc.w)
        discard;
    fragColor = color;
}
