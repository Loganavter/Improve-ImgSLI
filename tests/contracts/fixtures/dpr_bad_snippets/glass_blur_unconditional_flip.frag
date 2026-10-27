# provenance: src/engine/gpu/shaders/glass_panel/glass_blur.frag:50 @ reconstructed
# rule: uv-flip-compensation
// RED fixture (shader): the glass blur flipped vUv.y unconditionally.
//
// Provenance: the shipped shader carries the note this snippet reconstructs
// (glass_blur.frag:19-26, same file, current tree):
//
//   "An earlier version of this shader ALSO flipped vUv.y here, on the theory
//    that a plain copyTexture doesn't reverse row order within its copied
//    block -- confirmed wrong via live re-test (content came out upside down):
//    don't reintroduce that flip here, it was one flip too many for a chain
//    that was already self-consistent without it."
//
// The commit that removed it is not reachable from this history (the shader
// arrived with the pre-v10.0.1 squash), so the body below is the documented
// pre-gate form: `vec2 uv = vec2(vUv.x, 1.0 - vUv.y);` with no `flipY` gate.
// The current, legal form is `mix(vUv.y, 1.0 - vUv.y, flipY)` -- it is the
// negative fixture `legal_gated_shader_flip.frag`.

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
    vec2 uv = vec2(vUv.x, 1.0 - vUv.y);
    vec4 sum = texture(srcTex, uv);
    fragColor = sum;
}
