#version 440

// Variant C1 (F5 re-open 2026-10-06): the text texture + 4x supersample +
// Lanczos downsample of variant A are gone. Text is per-glyph quads that
// sample a signed-distance-field atlas; the glyph edge is
//    sd = (tex - 0.5) * sdfRangePx   (negative inside, 0 at the edge)
// and the coverage is a smoothstep around sd == 0, so AA is
// resolution-independent. Synthetic bold shifts the edge:
//    sd -= weight/500 * pixel_size.
// The rounded-rect BACKGROUND is still procedural (mode 0, signed-distance
// rounded box), so both fragment paths share one pipeline.
//
// Output is premultiplied; the pipeline blend stays One / OneMinusSrcAlpha,
// and the mode-0 background quad is emitted before the mode-1 glyph quads so
//    result = text + bg * (1 - text.a)
// falls out of the fixed-function blend order.
//
// std140 block declared byte-for-byte identically in filename_overlay.vert
// (binding 0, 128 bytes); the Python side asserts "<32f" == 128 in passes.py.
layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;              // offset 0   pixel-space -> clip
    vec4 bgColor;          // offset 64  premultiplied rgba
    vec2 quadSizePx;       // offset 80  label quad size (device px, bg local space)
    vec2 pad0;             // offset 88
    float cornerRadiusPx;  // offset 96
    float bgEnabled;       // offset 100
    float sdfRangePx;      // offset 104 atlas decode range (logical px)
    float pixelSize;       // offset 108 logical font px (bold scale)
    float edgePx;          // offset 112 AA half-width in logical px
    float pad1;            // offset 116
    vec2 pad2;             // offset 120
};

layout(binding = 1) uniform sampler2D uAtlas;

layout(location = 0) in vec2 vTexCoord;
layout(location = 1) in vec4 vColor;
layout(location = 2) in vec2 vAux;

layout(location = 0) out vec4 fragColor;

// Standard rounded-box signed distance: < 0 inside, > 0 outside.
float roundedBoxSdf(vec2 p, vec2 halfSize, float radius)
{
    vec2 q = abs(p) - (halfSize - vec2(radius));
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - radius;
}

void main()
{
    vec4 outColor;
    if (vAux.x < 0.5)
    {
        // Mode 0: procedural rounded-rect background. vTexCoord is the label
        // quad's own 0..1 coordinate; quadSizePx is its device-px size.
        vec2 localPx = vTexCoord * quadSizePx;
        float bgCoverage = 0.0;
        if (bgEnabled > 0.5)
        {
            vec2 halfSize = quadSizePx * 0.5;
            float d = roundedBoxSdf(localPx - halfSize, halfSize, cornerRadiusPx);
            // 0.5px SDF erode with a 1px AA ramp centred on d == -0.5, matching
            // the retired CPU 0.5px inset so there is no seam at the edge.
            bgCoverage = clamp(-d, 0.0, 1.0);
        }
        outColor = bgColor * bgCoverage;
    }
    else
    {
        // Mode 1: glyph coverage sample. The atlas stores antialiased alpha
        // coverage (supersample+LANCZOS downscaled per glyph -- the glass-HUD
        // text-mask fix), NOT a signed-distance field, so there is no decode
        // or threshold that can saturate to 0/1: the edge gradient is the
        // coverage itself.
        float a = texture(uAtlas, vTexCoord).r;
        outColor = vColor * a;
    }
    fragColor = outColor;
}
