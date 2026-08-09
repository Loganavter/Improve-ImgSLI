#version 440

// Fullscreen-quad vertex shader for mip_downsample.frag (docs/dev/rendering/
// tile-array-atlas-plan.md Phase 9). corrMatrix here is NOT
// rhi.clipSpaceCorrMatrix() (that's identity for a visible QRhiWidget's own
// backend/context -- its later on-screen compositing absorbs the Y
// convention) -- it's an unconditional Y-flip, set once from the CPU side
// (MipCascadeGenerator._ensure_downsample_corr_buffer). This scratch render
// target is never composited to screen, so nothing else cancels that flip
// out; skipping it left each generated mip level's orientation alternating
// by level parity relative to level 0 (each level samples the previous
// level, which was itself already flipped once by this same pass).

layout(std140, binding = 2) uniform VertUBuf
{
    mat4 corrMatrix;
};

layout(location = 0) in vec2 position;
layout(location = 1) in vec2 texCoord;

layout(location = 0) out vec2 vTexCoord;

void main()
{
    gl_Position = corrMatrix * vec4(position, 0.0, 1.0);
    vTexCoord = texCoord;
}
