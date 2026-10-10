#version 440

// Variant A (F5 re-open 2026-10-06): the rounded-rect BACKGROUND is drawn
// here procedurally from the quad geometry (signed-distance rounded box)
// instead of being baked into the CPU raster. The texture now carries ONLY
// the text (transparent background) and is cached by content, so a width
// change only resizes the quad / shifts textRectPx -- no re-rasterize.
//
// Output is premultiplied: frag = text + bg * (1 - text.a); the pipeline
// blend stays One / OneMinusSrcAlpha (render/gpu_resources.initialize).
// Declared byte-for-byte identically in filename_overlay.vert (std140,
// binding 0, 128 bytes); the Python side asserts "<32f" == 128 in passes.py.
layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;              // offset 0
    vec4 bgColor;          // offset 64  premultiplied rgba
    vec2 quadSizePx;       // offset 80
    vec2 pad0;             // offset 88
    vec4 textRectPx;       // offset 96  quad-local text sample window
    float cornerRadiusPx;  // offset 112
    float bgEnabled;       // offset 116
    float textEnabled;     // offset 120
    float pad1;            // offset 124
};

layout(binding = 1) uniform sampler2D uTex;

layout(location = 0) in vec2 vTexCoord;
layout(location = 0) out vec4 fragColor;

// Standard rounded-box signed distance: < 0 inside, > 0 outside.
float roundedBoxSdf(vec2 p, vec2 halfSize, float radius)
{
    vec2 q = abs(p) - (halfSize - vec2(radius));
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - radius;
}

void main()
{
    vec2 localPx = vTexCoord * quadSizePx;

    float bgCoverage = 0.0;
    if (bgEnabled > 0.5)
    {
        vec2 halfSize = quadSizePx * 0.5;
        float d = roundedBoxSdf(localPx - halfSize, halfSize, cornerRadiusPx);
        // Reproduce the old CPU 0.5px inset (label_raster's
        // adjusted(0.5,0.5,-0.5,-0.5)) as a 0.5px SDF erode with a 1px-wide
        // AA ramp centred on d == -0.5, so there is no seam at the edge.
        bgCoverage = clamp(-d, 0.0, 1.0);
    }
    vec4 bg = bgColor * bgCoverage;

    vec4 text = vec4(0.0);
    if (textEnabled > 0.5)
    {
        vec2 tuv = (localPx - textRectPx.xy) / textRectPx.zw;
        vec2 inRange = step(vec2(0.0), tuv) * step(tuv, vec2(1.0));
        text = texture(uTex, tuv) * (inRange.x * inRange.y);
    }

    fragColor = text + bg * (1.0 - text.a);
}
