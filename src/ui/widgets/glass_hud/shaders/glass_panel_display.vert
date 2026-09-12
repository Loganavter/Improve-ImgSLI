#version 440

// Fullscreen-triangle vertex shader ("big triangle" technique) -- this
// widget's own render target is sized exactly to the sprite it blits, so no
// per-vertex uniform data (position, UV, correction matrix) is needed.

layout(location = 0) out vec2 vUv;

void main()
{
    vec2 pos = vec2((gl_VertexIndex << 1) & 2, gl_VertexIndex & 2);
    vUv = pos;
    gl_Position = vec4(pos * 2.0 - 1.0, 0.0, 1.0);
}