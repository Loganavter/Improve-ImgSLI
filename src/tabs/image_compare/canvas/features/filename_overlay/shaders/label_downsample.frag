#version 440

// Downsamples a filename label rasterized at SCALE x its own final device
// resolution (see render/label_raster.py's _LABEL_SUPERSAMPLE) down to that
// final resolution using a properly-scaled Lanczos-2 kernel, in one shader
// pass -- same technique and same kernel as
// shared/rendering/shaders/glass_panel/glass_text_downsample.frag (that
// one isn't reused directly to avoid a cross-feature shader-path
// dependency; this file is an intentional duplicate, not a divergence).
// Replaces this feature's previous CPU-side downscale (PIL LANCZOS when a
// usable font file path was found, a much lower quality Qt QPainter
// implicit scale otherwise) -- see
// docs/dev/rendering/glass-panel-text-vibrancy-plan.md's bug 18 for why
// unifying on this GPU pass, not just fixing the CPU fallback path, was
// the chosen fix.
//
// SCALE must match render/label_raster.py's own _LABEL_SUPERSAMPLE (kept
// in sync by comment on both sides, same convention as
// glass_panel._TEXT_MASK_SUPERSAMPLE).
const float SCALE = 4.0;
const int RADIUS = 8; // int(2.0 * SCALE) -- see this pass's own docstring above.

layout(binding = 0) uniform sampler2D srcTex;

layout(location = 0) in vec2 vUv;
layout(location = 0) out vec4 fragColor;

float sinc(float x)
{
    if (abs(x) < 1e-5)
        return 1.0;
    float px = 3.14159265358979 * x;
    return sin(px) / px;
}

float lanczos2(float x)
{
    if (abs(x) >= 2.0)
        return 0.0;
    return sinc(x) * sinc(x * 0.5);
}

void main()
{
    vec2 srcSize = vec2(textureSize(srcTex, 0));
    vec2 srcTexel = 1.0 / srcSize;
    vec2 centerPx = vUv * srcSize;
    vec2 baseTexel = floor(centerPx);

    vec4 sum = vec4(0.0);
    float weightSum = 0.0;
    for (int iy = -RADIUS; iy < RADIUS; iy++)
    {
        for (int ix = -RADIUS; ix < RADIUS; ix++)
        {
            vec2 sampleTexel = baseTexel + vec2(float(ix), float(iy)) + 0.5;
            vec2 dist = (sampleTexel - centerPx) / SCALE;
            float w = lanczos2(dist.x) * lanczos2(dist.y);
            if (w == 0.0)
                continue;
            vec2 uv = sampleTexel * srcTexel;
            sum += textureLod(srcTex, uv, 0.0) * w;
            weightSum += w;
        }
    }
    fragColor = sum / max(weightSum, 1e-5);
}
