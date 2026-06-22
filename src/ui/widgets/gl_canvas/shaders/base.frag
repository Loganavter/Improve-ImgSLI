#version 440

layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;
    vec2 offset;
    float zoom;
    float splitPosition;
    vec4 letterbox1;
    vec4 letterbox2;
    int isHorizontal;
    int channelMode;
    int diffMode;
    int diffSourceReady;
    float diffThreshold;
};

layout(binding = 1) uniform sampler2D image1;
layout(binding = 2) uniform sampler2D image2;
layout(binding = 3) uniform sampler2D imageDiff;

layout(location = 0) in vec2 vTexCoord;
layout(location = 0) out vec4 fragColor;

vec4 applyChannel(vec4 color, int mode)
{
    if (mode == 1) return vec4(color.r, 0.0, 0.0, color.a);
    if (mode == 2) return vec4(0.0, color.g, 0.0, color.a);
    if (mode == 3) return vec4(0.0, 0.0, color.b, color.a);
    if (mode == 4) {
        float luma = dot(color.rgb, vec3(0.299, 0.587, 0.114));
        return vec4(luma, luma, luma, color.a);
    }
    return color;
}

float luminance(vec3 color)
{
    return dot(color, vec3(0.299, 0.587, 0.114));
}

vec4 sampleImage(sampler2D tex, vec2 uv)
{
    return applyChannel(texture(tex, uv), channelMode);
}

vec4 computeEdge(sampler2D tex, vec2 uv)
{
    vec2 stepPx = 1.0 / vec2(textureSize(tex, 0));
    float tl = luminance(sampleImage(tex, uv + vec2(-stepPx.x, -stepPx.y)).rgb);
    float t  = luminance(sampleImage(tex, uv + vec2(0.0, -stepPx.y)).rgb);
    float tr = luminance(sampleImage(tex, uv + vec2(stepPx.x, -stepPx.y)).rgb);
    float l  = luminance(sampleImage(tex, uv + vec2(-stepPx.x, 0.0)).rgb);
    float r  = luminance(sampleImage(tex, uv + vec2(stepPx.x, 0.0)).rgb);
    float bl = luminance(sampleImage(tex, uv + vec2(-stepPx.x, stepPx.y)).rgb);
    float b  = luminance(sampleImage(tex, uv + vec2(0.0, stepPx.y)).rgb);
    float br = luminance(sampleImage(tex, uv + vec2(stepPx.x, stepPx.y)).rgb);
    float gx = -tl - 2.0 * l - bl + tr + 2.0 * r + br;
    float gy = -tl - 2.0 * t - tr + bl + 2.0 * b + br;
    float edge = smoothstep(0.05, 0.3, sqrt(gx * gx + gy * gy));
    return vec4(edge, edge, edge, 1.0);
}

void main()
{
    vec2 center = vec2(0.5);
    vec2 uv = (vTexCoord - center) / zoom + center - offset;
    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
        fragColor = vec4(0.0);
        return;
    }

    bool useFirst = (isHorizontal != 0 ? vTexCoord.y : vTexCoord.x) < splitPosition;
    vec4 letterbox = useFirst ? letterbox1 : letterbox2;
    vec2 sampleUV = (uv - letterbox.xy) / letterbox.zw;
    if (sampleUV.x < 0.0 || sampleUV.x > 1.0 || sampleUV.y < 0.0 || sampleUV.y > 1.0) {
        fragColor = vec4(0.0);
        return;
    }

    vec4 color1 = sampleImage(image1, sampleUV);
    vec4 color2 = sampleImage(image2, sampleUV);

    if (diffMode == 1) {
        vec3 diff = abs(color1.rgb - color2.rgb);
        float maxDiff = max(diff.r, max(diff.g, diff.b));
        fragColor = maxDiff > diffThreshold ? vec4(1.0, 0.35, 0.47, 1.0) : color1;
    } else if (diffMode == 2) {
        vec3 diff = abs(color1.rgb - color2.rgb);
        float gray = clamp(luminance(diff) * 4.0, 0.0, 1.0);
        fragColor = vec4(gray, gray, gray, 1.0);
    } else if (diffMode == 3) {
        fragColor = useFirst ? computeEdge(image1, sampleUV) : computeEdge(image2, sampleUV);
    } else if (diffMode == 4 && diffSourceReady != 0) {
        fragColor = applyChannel(texture(imageDiff, sampleUV), channelMode);
    } else {
        fragColor = useFirst ? color1 : color2;
    }
}
