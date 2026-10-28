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
    // Same unit rule as guides.frag and filename_overlay (one DEVICE px of
    // feather, src/tabs/image_compare/canvas/features/filename_overlay/
    // passes.py:394): `resolution` is the widget's LOGICAL size (pack_capture) and centerPx/radiusPx/lineWidthPx
    // are packed in that same space, so one device px is 1/dpr LOGICAL px,
    // taken off the fragment footprint (0.5 at DPR 2, 1.0 at DPR 1). A fixed
    // +/-1.15 here made the capture ring feather ~2x the labels' width at DPR 2.
    float featherPx = 0.5 * (fwidth(fragPx.x) + fwidth(fragPx.y));
    float halfWidth = max(0.5, lineWidthPx * 0.5); // LOGICAL px, same space
    float ring = 1.0 - smoothstep(
        max(0.0, halfWidth - featherPx),
        halfWidth + featherPx,
        delta
    );
    if (ring <= 0.01) discard;
    fragColor = vec4(color.rgb, color.a * ring);
}
