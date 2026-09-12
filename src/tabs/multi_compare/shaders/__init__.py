"""GLSL shaders for multi-compare grid rendering."""

from ui.widgets.canvas.runtime import should_prefer_gles


def _prolog(*, fragment: bool = False) -> str:
    if not should_prefer_gles():
        return "#version 330 core\n"
    lines = ["#version 300 es", "precision highp float;", "precision highp int;"]
    if fragment:
        lines.append("precision mediump sampler2D;")
    return "\n".join(lines) + "\n"


VERTEX_SHADER = _prolog() + """
layout (location = 0) in vec2 aPos;
layout (location = 1) in vec2 aTexCoord;
out vec2 TexCoord;
void main() {
    gl_Position = vec4(aPos, 0.0, 1.0);
    TexCoord = aTexCoord;
}
"""

FRAGMENT_SHADER = _prolog(fragment=True) + """
in vec2 TexCoord;
out vec4 FragColor;

uniform sampler2D image;
uniform vec2 panOffset;   // normalized pan in image-uv
uniform float zoom;       // >=1 means zoom in
uniform vec2 fitScale;    // per-axis scale (<=1) to preserve aspect inside cell

void main() {
    // 1) Aspect-preserve fit: shrink along the limiting axis so the image
    //    keeps its aspect ratio inside the cell. The unused region becomes
    //    out-of-bounds → letterboxed black.
    vec2 uv = (TexCoord - vec2(0.5)) / fitScale + vec2(0.5);

    // 2) Zoom + pan in image-uv units.
    uv = (uv - vec2(0.5)) / zoom + vec2(0.5) - panOffset;

    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
        FragColor = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }
    FragColor = texture(image, uv);
}
"""
