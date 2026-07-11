#version 440

layout(location = 0) in vec2 position;
layout(location = 1) in vec2 texCoord;

layout(std140, binding = 0) uniform UBuf
{
    mat4 mvp;
    vec2 offset;
    vec2 zoom;
    float splitPosition;
    vec4 letterbox1;
    vec4 letterbox2;
    int isHorizontal;
    int channelMode;
    int diffMode;
    int diffSourceReady;
    float diffThreshold;
    vec4 tileRect1;
    vec4 tileRect2;
};

layout(location = 0) out vec2 vTexCoord;

void main()
{
    gl_Position = mvp * vec4(position, 0.0, 1.0);
    vTexCoord = texCoord;
}
