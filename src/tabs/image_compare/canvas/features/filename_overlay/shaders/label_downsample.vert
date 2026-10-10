#version 440

// Fullscreen-triangle vertex shader for label_downsample.frag -- same "big
// triangle" trick as shared/rendering/shaders/glass_panel/glass_panel_pass.vert
// (that one isn't reused directly to avoid a cross-feature shader-path
// dependency; this file is an intentional duplicate, not a divergence).

layout(location = 0) out vec2 vUv;

void main()
{
    vec2 pos = vec2((gl_VertexIndex << 1) & 2, gl_VertexIndex & 2);
    vUv = pos;
    gl_Position = vec4(pos * 2.0 - 1.0, 0.0, 1.0);
}
