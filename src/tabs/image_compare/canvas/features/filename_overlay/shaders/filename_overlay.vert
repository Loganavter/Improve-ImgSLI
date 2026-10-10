#version 440

// Variant C1 (F5 re-open 2026-10-06): text is per-glyph quads sampling a
// single-channel signed-distance-field atlas (filename_overlay.frag). The
// label background is a separate mode-0 quad drawn through the same pipeline,
// so background + text composite in one pass. All positions arrive in the
// pass's pixel space (y-down); the uniform's mvp is pixel -> clip.
//
// std140 block declared byte-for-byte identically in filename_overlay.frag
// (binding 0, 128 bytes); the Python side asserts "<32f" == 128 in passes.py.
layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;              // offset 0   pixel-space -> clip
    vec4 bgColor;          // offset 64  premultiplied rgba
    vec2 quadSizePx;       // offset 80  label quad size (device px, bg local space)
    vec2 pad0;             // offset 88
    float cornerRadiusPx;  // offset 96
    float bgEnabled;       // offset 100
    float sdfRangePx;      // offset 104 atlas decode range (logical px)
    float pixelSize;       // offset 108 logical font px (bold scale)
    float edgePx;          // offset 112 AA half-width in logical px
    float pad1;            // offset 116
    vec2 pad2;             // offset 120
};

// location 0 = position (px), 1 = atlas uv, 2 = premultiplied color,
// 3 = aux (x = mode, y = font weight).
layout(location = 0) in vec2 aPos;
layout(location = 1) in vec2 aUV;
layout(location = 2) in vec4 aColor;
layout(location = 3) in vec2 aAux;

layout(location = 0) out vec2 vTexCoord;
layout(location = 1) out vec4 vColor;
layout(location = 2) out vec2 vAux;

void main()
{
    gl_Position = mvp * vec4(aPos, 0.0, 1.0);
    vTexCoord = aUV;
    vColor = aColor;
    vAux = aAux;
}
