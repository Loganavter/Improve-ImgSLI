#version 440

layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;
    vec2 resolution;
    vec2 startPx;
    vec2 endPx;
    float startRadiusPx;
    float endRadiusPx;
    float lineWidthPx;
    float padding;
    vec4 color;
};

layout(location = 0) in vec2 vTexCoord;
layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 fragPx = vTexCoord * resolution;
    vec2 segment = endPx - startPx;
    float segmentLength = length(segment);
    if (segmentLength <= 0.0001) discard;
    vec2 direction = segment / segmentLength;
    float sourceOverlap = max(lineWidthPx * 2.0, startRadiusPx * 0.08);
    float startCut = max(0.0, startRadiusPx - sourceOverlap);
    float endCut = max(0.0, endRadiusPx);
    if (segmentLength - startCut - endCut <= 0.0001) discard;
    vec2 clippedStart = startPx + direction * startCut;
    vec2 clippedEnd = endPx - direction * endCut;
    vec2 clippedSegment = clippedEnd - clippedStart;
    float lengthSquared = dot(clippedSegment, clippedSegment);
    if (lengthSquared <= 0.0001) discard;
    float t = dot(fragPx - clippedStart, clippedSegment) / lengthSquared;
    if (t < 0.0 || t > 1.0) discard;
    float distanceToLine = distance(
        fragPx, clippedStart + clippedSegment * t
    );
    // EVERY px below is a LOGICAL px, not a device px: `resolution` is packed
    // from the widget's logical size (ctx.width/height, see passes.py's
    // pack_guides call) and the span geometry -- startPx/endPx, radii,
    // lineWidthPx -- arrives in that same space. A fixed +/-1.15 feather is
    // therefore 2.3 logical px on every display: exactly 2.3 device px at
    // DPR 1 but 4.6 device px at DPR 2, i.e. the guides/rings feather to
    // ~2x the width the labels do on a HiDPI screen.
    //
    // The app-wide rule is one DEVICE px of feather: filename_overlay converts
    // it into its own sd unit in Python
    // (src/tabs/image_compare/canvas/features/filename_overlay/passes.py:394,
    // `edge_px = 1.0 / (zoom_scale * dpr)`). Same rule here, expressed in this
    // shader's own unit -- one device px is 1/dpr LOGICAL px, read off the
    // fragment's own footprint instead of adding a dpr uniform that prepare()
    // would have to resolve (device px belongs to the raster, not upstream --
    // docs/dev/rendering/coordinate-systems.md). fragPx advances one logical px
    // per logical px, i.e. 1/dpr per DEVICE fragment, on both axes (the quad
    // maps 1:1 onto the target): 1.0 at DPR 1, 0.5 at DPR 2, 0.8 at DPR 1.25.
    float featherPx = 0.5 * (fwidth(fragPx.x) + fwidth(fragPx.y));
    // Half-width floor, also LOGICAL px (matches the 1 px floor the resolver
    // applies to the stroke itself, guides/overlay_model.py's `line_width`).
    float halfWidth = max(0.5, lineWidthPx * 0.5);
    float alpha = 1.0 - smoothstep(
        max(0.0, halfWidth - featherPx),
        halfWidth + featherPx,
        distanceToLine
    );
    if (alpha <= 0.01) discard;
    fragColor = vec4(color.rgb, color.a * alpha);
}
