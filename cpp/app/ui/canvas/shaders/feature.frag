#version 440

layout(location = 0) in vec2 uv;
layout(location = 0) out vec4 fragColor;

layout(std140, binding = 0) uniform Feature {
    mat4 clipSpaceCorrection;
    vec4 viewport;
    vec4 params0;
    vec4 params1;
    vec4 params2;
    vec4 color;
} uniforms;

layout(binding = 1) uniform sampler2D image1;
layout(binding = 2) uniform sampler2D image2;

float lineDistance(vec2 point, vec2 start, vec2 end)
{
    vec2 segment = end - start;
    float denom = max(dot(segment, segment), 0.000001);
    float t = clamp(dot(point - start, segment) / denom, 0.0, 1.0);
    return length(point - (start + segment * t));
}

vec4 splitSample(vec2 sampleUv)
{
    bool horizontal = uniforms.params0.y > 0.5;
    float coordinate = horizontal ? sampleUv.y : sampleUv.x;
    return coordinate <= uniforms.params0.x
        ? texture(image1, sampleUv)
        : texture(image2, sampleUv);
}

void main()
{
    float mode = uniforms.params0.w;
    float width = max(uniforms.viewport.x, 1.0);
    float height = max(uniforms.viewport.y, 1.0);
    vec2 aspect = vec2(width / height, 1.0);
    vec2 capture = uniforms.params1.xy;
    vec2 target = uniforms.params1.zw;
    float radius = uniforms.params2.x;
    float zoom = max(uniforms.params2.y, 1.0);
    float stroke = uniforms.params2.z / height;

    fragColor = vec4(0.0);

    if (mode < 1.5) {
        float coordinate = uniforms.params0.y > 0.5 ? uv.y : uv.x;
        float axis = uniforms.params0.y > 0.5 ? height : width;
        float distancePx = abs(coordinate - uniforms.params0.x) * axis;
        if (distancePx <= uniforms.params0.z * 0.5) {
            fragColor = uniforms.color;
        }
    } else if (mode < 2.5) {
        float distanceToTarget = length((uv - target) * aspect);
        if (distanceToTarget <= radius) {
            vec2 sampleUv = capture + (uv - target) / zoom;
            fragColor = splitSample(clamp(sampleUv, vec2(0.0), vec2(1.0)));
        }
    } else if (mode < 3.5) {
        float distanceToGuide = lineDistance(
            uv * aspect,
            capture * aspect,
            target * aspect);
        if (distanceToGuide <= stroke) {
            fragColor = uniforms.color;
        }
    } else if (mode < 4.5) {
        float d = abs(length((uv - capture) * aspect) - radius / zoom);
        if (d <= stroke) {
            fragColor = uniforms.color;
        }
    } else if (mode < 5.5) {
        bool leftLabel = uv.x < 0.36 && uv.y < 0.075;
        bool rightLabel = uv.x > 0.64 && uv.y < 0.075;
        if (leftLabel || rightLabel) {
            fragColor = uniforms.color;
        }
    } else if (mode < 6.5) {
        vec2 centerDistance = abs(uv - vec2(0.5));
        if (centerDistance.x < 0.22 || centerDistance.y < 0.22) {
            fragColor = uniforms.color;
        }
    } else {
        float d = abs(length((uv - target) * aspect) - radius);
        if (d <= stroke * 1.5) {
            fragColor = uniforms.color;
        }
    }
}
