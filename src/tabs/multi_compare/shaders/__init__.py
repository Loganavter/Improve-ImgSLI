"""GLSL shaders for multi-compare grid rendering."""

from ui.widgets.gl_canvas.runtime import should_prefer_gles

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
uniform vec2 panOffset;   // normalized pan in image-space
uniform float zoom;       // >=1 means zoom in

void main() {
    vec2 uv = TexCoord;

    // Apply zoom + pan: center-based
    vec2 center = vec2(0.5);
    uv = (uv - center) / zoom + center - panOffset;

    // Out-of-bounds → black
    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
        FragColor = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }

    FragColor = texture(image, uv);
}
"""
