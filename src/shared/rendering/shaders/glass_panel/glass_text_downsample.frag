#version 440

// Downsamples text_mask_tex (rasterized at SCALE x this panel's own device
// resolution, see ui/widgets/glass_hud/text_mask.py's _TEXT_MASK_SUPERSAMPLE) down to
// device resolution using a properly-scaled Lanczos-2 kernel, in one shader
// pass -- replaces an earlier version of this pipeline that used GPU
// hardware mip generation (QRhi's generateMips(), a plain box filter per
// level) for this same downscale: box-filtered mips are visibly softer than
// Lanczos on the sharp alpha edges a rasterized glyph mask is made of (a
// 2-level box chain approximates a triangle/bilinear filter in the
// frequency domain, not a windowed sinc) -- reported live as "looks
// trilinear, not Lanczos" despite textureLod() landing on the exact right
// mip level. See docs/dev/rendering/glass-panel-text-vibrancy-plan.md's bug
// 17 for the full before/after.
//
// SCALE must match ui.widgets.glass_hud._TEXT_MASK_SUPERSAMPLE /
// shared.rendering.glass_panel._TEXT_MASK_SUPERSAMPLE (kept in sync by
// comment on all three, same convention as those constants themselves).
const float SCALE = 4.0;
// Lanczos-2's own support radius is 2 source samples per destination sample
// at 1:1; downsampling by SCALE widens that support proportionally (a
// correctly *scaled* reconstruction filter, not the unscaled kernel
// evaluated directly against source texels -- the latter would just alias)
// -- see this pass's own docstring above. int(2.0 * SCALE) here, spelled as
// a literal since GLSL doesn't allow a non-const-expression array/loop
// bound derived from a `const float`.
const int RADIUS = 8;

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
    // Continuous source-space position (texel-index units) that this
    // destination pixel's center maps back to.
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
