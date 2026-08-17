#version 440

// Pass 1 of the glass-panel backdrop blur (horizontal half; glass_composite.frag
// does the vertical half + tint + border). srcTex here is a *scratch* texture
// this app's own canvas render pipeline already cropped out of its own
// colorTexture() via a plain GPU copyTexture (see
// shared.rendering.glass_panel.GlassPanelRenderer).
//
// copyTexture's *source rect* is Y-flipped on the Python side to select the
// correct rows at all (colorTexture()'s own row order is backend-native,
// e.g. bottom-up on OpenGL, not screen-top-down -- confirmed via GPU
// readback: without that flip, a bottom-anchored panel's crop was reading
// from near the *top* of the canvas instead). That flip only changes WHICH
// rows get selected, not how they're subsequently interpreted -- crop_tex,
// blur_tex, and composite_tex all stay internally consistent with each
// other (same convention throughout this module), and the final display
// widget's own on-screen compositing blit absorbs whatever that convention
// is, same as any other QRhiWidget's own output. An earlier version of this
// shader ALSO flipped vUv.y here, on the theory that a plain copyTexture
// doesn't reverse row order within its copied block -- confirmed wrong via
// live re-test (content came out upside down): don't reintroduce that flip
// here, it was one flip too many for a chain that was already
// self-consistent without it.

layout(std140, binding = 0) uniform UBuf
{
    vec2 direction;
    float radiusPx;
    float flipY; // 1.0 when colorTexture()'s rows are stored bottom-up (OpenGL)
};

layout(binding = 1) uniform sampler2D srcTex;

layout(location = 0) in vec2 vUv;
layout(location = 0) out vec4 fragColor;

const int TAPS = 8; // -8..8 inclusive => 17 samples

void main()
{
    // When the canvas's colorTexture() is stored bottom-up (backend-native on
    // OpenGL; rhi.isYUpInFramebuffer() == true), the Python side flips the
    // crop's sourceTopLeft to select the correct rows, which leaves crop_tex's
    // row order reversed relative to the panel's own coordinate space. Flip
    // the sample V here to compensate -- the second half of the pair that was
    // added-then-reverted as a "false trail" (see glass_panel.py's docstring);
    // the trail was false because the debug-dump tool was mirroring its ground
    // truth, not because the flips were wrong. Gate on a uniform (not on the
    // backend at compile time) so one qsb serves both row orders.
    vec2 uv = vec2(vUv.x, mix(vUv.y, 1.0 - vUv.y, flipY));

    vec2 texel = direction / vec2(textureSize(srcTex, 0));
    float sigma = max(radiusPx / 3.0, 0.6);

    vec4 sum = vec4(0.0);
    float weightSum = 0.0;
    for (int i = -TAPS; i <= TAPS; i++)
    {
        float fi = float(i);
        float w = exp(-(fi * fi) / (2.0 * sigma * sigma));
        sum += texture(srcTex, uv + texel * fi) * w;
        weightSum += w;
    }

    fragColor = sum / max(weightSum, 1e-5);
}
