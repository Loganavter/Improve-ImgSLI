#version 440

// Engine single-image tiled-array fragment shader (engine.gpu.tiled_image_view).
//
// vTexCoord is a framebuffer fraction. The slot chain is:
//   contentUV = (vTexCoord - letterbox.xy) / letterbox.zw
//   uv        = (contentUV - 0.5) / (fit * zoom) + 0.5 - pan
// (engine.cache.draw_plans.slot_visible_rect mirrors the same chain for tile
// selection). With letterbox = (0,0,1,1) this is the single full-canvas slot.
// The tile's own apron-padded image-fraction rect locates it within the array
// layer; tile content is uploaded 1:1 into the layer's top-left corner, so
// contentScale only rescales the UV used to address that corner.

layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;
    vec4 letterbox;
    vec2 pan;
    vec2 zoom;
    vec2 fit;
    vec2 _pad;
};

layout(binding = 1) uniform sampler2DArray tileArray;

layout(location = 0) in vec2 vTexCoord;
layout(location = 1) in vec4 vRect;
layout(location = 2) in vec2 vContentScale;
layout(location = 3) flat in int vLayer;

layout(location = 0) out vec4 fragColor;

void main()
{
    if (letterbox.z <= 0.0 || letterbox.w <= 0.0) {
        fragColor = vec4(0.0);
        return;
    }
    vec2 contentUV = (vTexCoord - letterbox.xy) / letterbox.zw;
    if (contentUV.x < 0.0 || contentUV.x > 1.0 || contentUV.y < 0.0 || contentUV.y > 1.0) {
        fragColor = vec4(0.0);
        return;
    }
    vec2 uv = (contentUV - vec2(0.5)) / (fit * zoom) + vec2(0.5) - pan;
    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
        fragColor = vec4(0.0);
        return;
    }
    vec2 tileUV = (uv - vRect.xy) / vRect.zw;
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
