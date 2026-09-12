#version 440

// Straight, unmodified blit of a glass panel's already-fully-composited
// sprite (shared.rendering.glass_panel.GlassPanelRenderer -- blur, tint,
// border, rounded crop, real alpha all already baked in). No Y-flip here:
// this samples srcTex the same way the old canvas-target blit pass did
// (features/glass_panel/passes.py, since removed) -- proven correct as-is,
// because glass_composite.frag already resolved this texture's own
// internal orientation to match normal top-down screen convention when it
// wrote it (see glass_blur.frag / glass_panel.py's crop-source Y-flip for
// where that correction actually happens).

layout(binding = 1) uniform sampler2D srcTex;

layout(location = 0) in vec2 vUv;
layout(location = 0) out vec4 fragColor;

void main()
{
    fragColor = texture(srcTex, vUv);
}