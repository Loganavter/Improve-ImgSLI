from .common import shader_prolog

BASE_VERTEX_SHADER_TEMPLATE = """
layout (location = 0) in vec2 aPos;
layout (location = 1) in vec2 aTexCoord;
out vec2 TexCoord;
void main() {
    gl_Position = vec4(aPos.x, aPos.y, 0.0, 1.0);
    TexCoord = aTexCoord;
}
"""

BASE_FRAGMENT_SHADER_TEMPLATE = """
in vec2 TexCoord;
out vec4 FragColor;

uniform float splitPosition;
uniform bool isHorizontal;
uniform vec2 offset;
uniform float zoom;

uniform sampler2D image1;
uniform sampler2D image2;
uniform sampler2D imageDiff;
uniform int channelMode; // 0=RGB, 1=R, 2=G, 3=B, 4=L
uniform int diffMode; // 0=off, 1=highlight, 2=grayscale, 3=edges, 4=ssim map
uniform bool diffSourceReady;
uniform float diffThreshold;
uniform bool useSourceTex;
uniform vec4 letterbox1; // offsetX, offsetY, scaleX, scaleY
uniform vec4 letterbox2; // offsetX, offsetY, scaleX, scaleY

vec4 applyChannel(vec4 c, int mode) {
    if (mode == 1) return vec4(c.r, 0.0, 0.0, c.a);
    if (mode == 2) return vec4(0.0, c.g, 0.0, c.a);
    if (mode == 3) return vec4(0.0, 0.0, c.b, c.a);
    if (mode == 4) { float l = dot(c.rgb, vec3(0.299, 0.587, 0.114)); return vec4(l, l, l, c.a); }
    return c;
}

float luminance(vec3 c) {
    return dot(c, vec3(0.299, 0.587, 0.114));
}

vec4 sampleImage(sampler2D tex, vec2 uv) {
    return applyChannel(texture(tex, uv), channelMode);
}

vec4 computeEdge(sampler2D tex, vec2 uv) {
    vec2 stepPx = 1.0 / vec2(textureSize(tex, 0));
    float tl = luminance(sampleImage(tex, uv + vec2(-stepPx.x, -stepPx.y)).rgb);
    float t  = luminance(sampleImage(tex, uv + vec2(0.0,       -stepPx.y)).rgb);
    float tr = luminance(sampleImage(tex, uv + vec2( stepPx.x, -stepPx.y)).rgb);
    float l  = luminance(sampleImage(tex, uv + vec2(-stepPx.x,  0.0)).rgb);
    float r  = luminance(sampleImage(tex, uv + vec2( stepPx.x,  0.0)).rgb);
    float bl = luminance(sampleImage(tex, uv + vec2(-stepPx.x,  stepPx.y)).rgb);
    float b  = luminance(sampleImage(tex, uv + vec2(0.0,        stepPx.y)).rgb);
    float br = luminance(sampleImage(tex, uv + vec2( stepPx.x,  stepPx.y)).rgb);
    float gx = -tl - 2.0*l - bl + tr + 2.0*r + br;
    float gy = -tl - 2.0*t - tr + bl + 2.0*b + br;
    float edge = smoothstep(0.05, 0.3, sqrt(gx * gx + gy * gy));
    return vec4(edge, edge, edge, 1.0);
}

void main() {
    vec2 center = vec2(0.5, 0.5);
    vec2 uv = (TexCoord - center) / zoom + center - offset;

    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
        FragColor = vec4(0.0, 0.0, 0.0, 0.0);
        return;
    }

    vec4 color;
    float coord = isHorizontal ? TexCoord.y : TexCoord.x;
    bool useFirst = coord < splitPosition;
    vec4 letterbox = useFirst ? letterbox1 : letterbox2;
    vec2 sampleUV = (uv - letterbox.xy) / letterbox.zw;
    if (sampleUV.x < 0.0 || sampleUV.x > 1.0 || sampleUV.y < 0.0 || sampleUV.y > 1.0) {
        FragColor = vec4(0.0, 0.0, 0.0, 0.0);
        return;
    }

    vec4 c1 = sampleImage(image1, sampleUV);
    vec4 c2 = sampleImage(image2, sampleUV);

    if (diffMode == 1) {
        vec3 diff = abs(c1.rgb - c2.rgb);
        float maxDiff = max(diff.r, max(diff.g, diff.b));
        color = maxDiff > diffThreshold ? vec4(1.0, 0.35, 0.47, 1.0) : c1;
    } else if (diffMode == 2) {
        vec3 diff = abs(c1.rgb - c2.rgb);
        float g = clamp(luminance(diff) * 4.0, 0.0, 1.0);
        color = vec4(g, g, g, 1.0);
    } else if (diffMode == 3) {
        color = useFirst ? computeEdge(image1, sampleUV) : computeEdge(image2, sampleUV);
    } else if (diffMode == 4 && diffSourceReady) {
        color = applyChannel(texture(imageDiff, sampleUV), channelMode);
    } else {
        color = useFirst ? c1 : c2;
    }

    FragColor = color;
}
"""


def build_base_vertex_shader(is_gles: bool) -> str:
    return f"{shader_prolog(is_gles)}\n{BASE_VERTEX_SHADER_TEMPLATE}"


def build_base_fragment_shader(is_gles: bool) -> str:
    return f"{shader_prolog(is_gles, fragment=True)}\n{BASE_FRAGMENT_SHADER_TEMPLATE}"
