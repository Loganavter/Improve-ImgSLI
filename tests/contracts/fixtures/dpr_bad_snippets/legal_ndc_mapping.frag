# provenance: src/tabs/image_compare/canvas/features/grid_dividers/shaders/grid_divider.frag:22 @ 230431a52
# rule: none
// LEGAL fixture: the UV -> NDC mapping, not a flip compensation.
//
// Verbatim from the shipped shader. `1.0 - vTexCoord.y * 2.0` is the standard
// screen-space (y down) to clip-space (y up) conversion every pixel-space quad
// performs; the backend convention is applied afterwards by the clip matrix
// (`engine/gpu/rt_y_orientation.composited_clip_correction`). The `* 2.0` is
// what distinguishes the mapping from a raster flip, and rule
// `uv-flip-compensation` must not fire on it.
//
// Same line in: focus_dim.frag:22, slot_array.vert:41, base_array.vert:85.

#version 440

layout(location = 0) in vec2 vTexCoord;

void main()
{
    vec2 ndc = vec2(vTexCoord.x * 2.0 - 1.0, 1.0 - vTexCoord.y * 2.0);
    gl_Position = vec4(ndc, 0.0, 1.0);
}
