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
    float halfWidth = max(0.5, lineWidthPx * 0.5);
    float alpha = 1.0 - smoothstep(
        max(0.0, halfWidth - 1.15),
        halfWidth + 1.15,
        distanceToLine
    );
    if (alpha <= 0.01) discard;
    fragColor = vec4(color.rgb, color.a * alpha);
}
