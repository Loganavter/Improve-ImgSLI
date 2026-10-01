#version 440

// Quick Look single-source tiled-array fragment shader (task-ql-tiles-w1).
//
// vTexCoord is a framebuffer fraction. With the whole framebuffer as the
// single slot, the image-space UV is the same fit/zoom/pan chain
// preview_zoom.py uses (and engine.cache.draw_plans.slot_visible_rect
// mirrors): uv = (screen - 0.5) / (fit * zoom) + 0.5 - pan. The tile's own
// apron-padded image-fraction rect locates it within the array layer; tile
// content is uploaded 1:1 into the top-left of its layer, so contentScale
// just rescales the UV used to address that corner.

layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;
    vec2 pan;
    vec2 zoom;
    vec2 fit;
    vec2 _pad;
};

layout(binding = 1) uniform sampler2DArray tileArray;

layout(location = 0) in vec2 vTexCoord;
layout(location = 1) in vec4 vRect1;
layout(location = 2) in vec2 vContentScale;
layout(location = 3) flat in int vLayer;

layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 uv = (vTexCoord - vec2(0.5)) / (fit * zoom) + vec2(0.5) - pan;
    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
        fragColor = vec4(0.0);
        return;
    }
    vec2 tileUV = (uv - vRect1.xy) / vRect1.zw;
    // Micro-seam tolerance: adjacent tile rects share an edge at 0/1 in
    // tileUV; float rounding can make both sides compute a hair outside
    // [0,1] and both discard (transparent grid seam). Expand by 1e-3 so the
    // 1px apron overlap always covers the boundary.
    if (tileUV.x < -0.001 || tileUV.x > 1.001 || tileUV.y < -0.001 || tileUV.y > 1.001) {
        fragColor = vec4(0.0);
        return;
    }
    vec2 arrUV = tileUV * vContentScale;
    fragColor = texture(tileArray, vec3(arrUV, float(vLayer)));
}
