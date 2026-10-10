#version 440

layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;
    // Focus-dim bar as pre-clip NDC bounds (x0, y0, x1, y1); the fragment
    // shader discards everything outside, so one fullscreen-quad draw per
    // bar paints exactly the old raster bar coverage.
    vec4 rectNdc;
    vec4 color;
};

layout(location = 0) in vec2 position;
layout(location = 1) in vec2 texCoord;

layout(location = 0) out vec2 vTexCoord;

void main()
{
    gl_Position = mvp * vec4(position, 0.0, 1.0);
    vTexCoord = texCoord;
}
