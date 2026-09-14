#version 440

// Generates one mip level of one layer of the shared tile texture array
// (docs/dev/rendering/tile-array-atlas-plan.md Phase 9). Replaces
// QRhiResourceUpdateBatch.generateMips, which regenerates every layer of the
// array in one call -- O(array capacity) GPU work per dirtied tile instead
// of O(1). One draw of this shader (a single fullscreen-quad pass targeting
// exactly this (layer, level) via QRhiColorAttachment.setLayer/setLevel)
// produces one destination level from the previous level;
// MipCascadeGenerator cascades this call from level 1 up to the full chain
// for a dirty layer. A single bilinear tap of the source level at the same
// UV is a standard box-downsample for an exact 2x size step (what
// glGenerateMipmap itself does per level), so no manual 2x2 averaging is
// needed.

layout(std140, binding = 0) uniform UBuf
{
    int layer;
    int srcLevel;
    int _pad0;
    int _pad1;
};

layout(binding = 1) uniform sampler2DArray tileArray;

layout(location = 0) in vec2 vTexCoord;
layout(location = 0) out vec4 fragColor;

void main()
{
    fragColor = textureLod(tileArray, vec3(vTexCoord, float(layer)), float(srcLevel));
}
