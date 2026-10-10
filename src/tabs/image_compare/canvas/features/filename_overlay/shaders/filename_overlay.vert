#version 440

// Variant A: the label background is procedural (signed-distance rounded box
// in filename_overlay.frag), so this block carries the quad geometry the
// fragment stage needs in addition to the clip-space matrix. Declared
// byte-for-byte identically in filename_overlay.frag (std140, binding 0,
// 128 bytes); the Python side asserts "<32f" == 128 in passes.py.
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

layout(location = 0) in vec2 aPos;
layout(location = 1) in vec2 aUV;

layout(location = 0) out vec2 vTexCoord;

void main()
{
    gl_Position = mvp * vec4(aPos, 0.0, 1.0);
    vTexCoord = aUV;
}
