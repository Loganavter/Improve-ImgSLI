#version 440

layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;
    vec4 quadBounds;
    vec2 magPan;
    vec2 _pad0;
    float magZoom;
    float radius_px;
    float borderWidth;
    float internalSplit;
    vec4 borderColor;
    vec4 combDividerColor;
    float combDividerThickness;
    float diffThreshold;
    int   combHorizontal;
    int   showCombDivider;
    int   useCircleMask;
    int   magGpuSampling;
    int   magCombined;
    int   magSourceMode;
    int   magDiffMode;
    int   magChannelMode;
    int   magInterpMode;
    int   _pad1;
    vec4 uvRect1;
    vec4 uvRect2;
};

layout(location = 0) in vec2 aPos;
layout(location = 1) in vec2 aTexCoord;

layout(location = 0) out vec2 TexCoord;

void main()
{
    float x = mix(quadBounds.x, quadBounds.z, aTexCoord.x);
    float y = mix(quadBounds.y, quadBounds.w, 1.0 - aTexCoord.y);
    x = x * magZoom + magPan.x * magZoom * 2.0;
    y = y * magZoom - magPan.y * magZoom * 2.0;
    gl_Position = mvp * vec4(x, y, 0.0, 1.0);
    TexCoord = aTexCoord;
}
