#version 440

// Shared fullscreen-triangle vertex shader for the glass-panel blur/composite
// passes (glass_blur.frag, glass_composite.frag) -- both passes render into a
// scratch texture sized exactly to one panel, so no per-vertex uniform data
// (position, UV) is needed beyond the "big triangle" trick.

layout(location = 0) out vec2 vUv;

void main()
{
    vec2 pos = vec2((gl_VertexIndex << 1) & 2, gl_VertexIndex & 2);
    vUv = pos;
    gl_Position = vec4(pos * 2.0 - 1.0, 0.0, 1.0);
}
