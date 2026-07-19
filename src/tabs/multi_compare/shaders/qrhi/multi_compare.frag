#version 440

layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;
    vec2 panOffset;
    vec2 fitScale;
    float zoom;
    float _pad0;
    float _pad1;
    float _pad2;
    vec4 tileRect;
    // Composition letterbox in framebuffer UV (xy = origin, zw = size).
    vec4 letterbox;
    // Slot cell in composition/content UV (xy = origin, zw = size).
    vec4 slotRect;
};

layout(binding = 1) uniform sampler2D image;

layout(location = 0) in vec2 TexCoord;
layout(location = 0) out vec4 FragColor;

void main()
{
    // Outer letterbox (same model as image_compare canvasLetterbox): map
    // framebuffer UV into composition content UV. Outside → transparent so
    // beginPass clear / other slots show through under SrcAlpha blend.
    if (letterbox.z <= 0.0 || letterbox.w <= 0.0) {
        FragColor = vec4(0.0);
        return;
    }
    vec2 contentUV = (TexCoord - letterbox.xy) / letterbox.zw;
    if (contentUV.x < 0.0 || contentUV.x > 1.0 || contentUV.y < 0.0 || contentUV.y > 1.0) {
        FragColor = vec4(0.0);
        return;
    }

    if (slotRect.z <= 0.0 || slotRect.w <= 0.0) {
        FragColor = vec4(0.0);
        return;
    }
    vec2 slotUV = (contentUV - slotRect.xy) / slotRect.zw;
    if (slotUV.x < 0.0 || slotUV.x > 1.0 || slotUV.y < 0.0 || slotUV.y > 1.0) {
        FragColor = vec4(0.0);
        return;
    }

    // Slot-local fit → zoom → pan (unchanged math; TexCoord used to be the
    // slot quad's UV, now derived from content UV via slotRect).
    vec2 uv = (slotUV - vec2(0.5)) / fitScale + vec2(0.5);
    uv = (uv - vec2(0.5)) / zoom + vec2(0.5) - panOffset;
    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
        FragColor = vec4(0.0);
        return;
    }
    // Tiling (docs/dev/TILED_RENDERING_DESIGN.md pattern, reused for
    // multi_compare via shared.rendering.tile_texture_service): the bound
    // texture may be just one GPU tile of a larger source image, not the
    // whole thing. tileRect is that tile's rect in normalized slot-image
    // space; a fragment only lights up on the one draw call (of the N
    // issued this frame for this slot) whose tile actually covers it.
    // N=1 (tileRect == (0,0,1,1)) makes tileUV == uv, unchanged from
    // pre-tiling behavior.
    vec2 tileUV = (uv - tileRect.xy) / tileRect.zw;
    if (tileUV.x < 0.0 || tileUV.x > 1.0 || tileUV.y < 0.0 || tileUV.y > 1.0) {
        FragColor = vec4(0.0);
        return;
    }
    FragColor = texture(image, tileUV);
}
