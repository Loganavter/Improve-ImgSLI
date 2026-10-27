# provenance: src/engine/gpu/shaders/glass_panel/glass_blur.frag:50 @ 230431a52
# rule: none
// LEGAL fixture: the gated form of the same flip.
//
// Verbatim from the shipped shader. The flip is behind a uniform that the
// Python side fills from `rt_y_orientation.widget_texture_needs_y_flip(rhi)`
// (`engine/gpu/glass_panel.py:774`), so the shader never decides a backend
// convention on its own — the `WIDGET_TEXTURE` case does.
//
// Keeping this next to `glass_blur_unconditional_flip.frag` is the precision
// proof for rule `uv-flip-compensation`: gate on `flipY`/`flip_y` or `mix(` and
// the detector must stay quiet.

#version 440

layout(std140, binding = 0) uniform UBuf
{
    vec2 direction;
    float radiusPx;
    float flipY;
};

layout(binding = 1) uniform sampler2D srcTex;

layout(location = 0) in vec2 vUv;
layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 uv = vec2(vUv.x, mix(vUv.y, 1.0 - vUv.y, flipY));
    fragColor = texture(srcTex, uv);
}
