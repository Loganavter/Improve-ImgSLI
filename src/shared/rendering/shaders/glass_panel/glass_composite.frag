#version 440

// Pass 2 of the glass-panel backdrop blur: vertical half of the same
// separable Gaussian (see glass_blur.frag) combined with tint and a rounded
// rounded-rect border/crop. This is the app-owned, canvas-pipeline
// replacement for sli-ui-toolkit's LiquidGlassFillWidget's
// liquid_glass_composite.frag -- same math (ported verbatim: roundedRectSD,
// tint mix, hard step()-based border/crop -- see that file's git history for
// why AA was dropped in favor of a hard edge), minus the cross-widget srcTex
// binding that shader used to fake a "raw backdrop outside the crop": this
// pass only ever samples its own scratch blur texture (already this panel's
// own backdrop, already in this panel's own coordinate space) and outputs
// real alpha=0 outside the rounded shape directly.

layout(std140, binding = 0) uniform UBuf
{
    vec2 direction;
    float radiusPx;
    float cornerRadiusPx;
    vec4 tint;
    vec2 panelSizePx;
    float borderWidthPx;
    float _pad0;
    vec4 borderColor;
    // IMGSLI_GLASS_PANEL_DEBUG_TINT=1 diagnostic only: a>0.5 shows this
    // panel's raw scratchTex (blur_tex) content *unmodified* -- no lensing/
    // chroma/tint/lighting math, just texture(scratchTex, vUv) -- ringed
    // with a per-panel-unique border color for identification. Tests
    // whether the sampled backdrop itself already contains foreign content
    // (a crop/blur-stage leak) before any of the "artistic" math the first
    // version of this test (flat fill, no texture read at all) would have
    // hidden regardless of whether that leak existed.
    vec4 debugTint;
};

layout(binding = 1) uniform sampler2D scratchTex;

layout(location = 0) in vec2 vUv;
layout(location = 0) out vec4 fragColor;

const int TAPS = 8; // -8..8 inclusive => 17 samples, same kernel as pass 1

float roundedRectSD(vec2 pointPx, vec2 halfSizePx, float radiusPx)
{
    vec2 q = abs(pointPx) - halfSizePx + radiusPx;
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - radiusPx;
}

// Analytic pseudo-surface-normal from the SDF's own gradient (central
// differences) -- points straight out of whichever edge/corner a pixel is
// nearest, which is exactly the "surface normal" a real glass rim-lighting
// model needs, without having to special-case straight edges vs. rounded
// corners separately.
vec2 roundedRectNormal(vec2 pointPx, vec2 halfSizePx, float radiusPx)
{
    float eps = 0.75;
    float dx = roundedRectSD(pointPx + vec2(eps, 0.0), halfSizePx, radiusPx)
             - roundedRectSD(pointPx - vec2(eps, 0.0), halfSizePx, radiusPx);
    float dy = roundedRectSD(pointPx + vec2(0.0, eps), halfSizePx, radiusPx)
             - roundedRectSD(pointPx - vec2(0.0, eps), halfSizePx, radiusPx);
    vec2 g = vec2(dx, dy);
    float len = length(g);
    return len > 1e-5 ? g / len : vec2(0.0, -1.0);
}

void main()
{
    vec2 halfSize = panelSizePx * 0.5;
    vec2 posPx = vUv * panelSizePx - halfSize;
    float d = roundedRectSD(posPx, halfSize, cornerRadiusPx);

    if (debugTint.a > 0.5)
    {
        vec3 raw = texture(scratchTex, vUv).rgb;
        float halfBorderDbg = max(borderWidthPx, 3.0) * 0.5;
        float outsideDbg = smoothstep(halfBorderDbg - 1.0, halfBorderDbg + 1.0, d);
        float innerDbg = smoothstep(-halfBorderDbg - 1.0, -halfBorderDbg + 1.0, d);
        float bandDbg = innerDbg * (1.0 - outsideDbg);
        vec3 color = mix(raw, debugTint.rgb, bandDbg);
        float alpha = 1.0 - outsideDbg;
        fragColor = vec4(color * alpha, alpha);
        return;
    }

    vec2 normal = roundedRectNormal(posPx, halfSize, cornerRadiusPx);

    // Cheap "lensing": bend the sampled backdrop inward near the panel's
    // own rim, peaking right at the edge and fading out a few px in --
    // Apple's Liquid Glass HIG describes background content as visibly
    // bent/warped near the glass boundary (real refraction), not merely
    // blurred; this approximates that cue with a UV offset along the SDF
    // normal instead of a true displacement/IOR simulation, which would
    // need the backdrop's depth and this pass has none.
    //
    // Both the falloff distance and the bend magnitude are capped relative
    // to the panel's own (smaller) dimension: on a small panel like
    // ZoomIndicator's chip, cornerRadiusPx can be a large fraction of the
    // whole height, and an uncapped bend there was pushing samples far
    // enough outside [0,1] UV to visibly wash the entire panel out via
    // ClampToEdge repeats -- not just a rim effect anymore.
    float minDim = min(panelSizePx.x, panelSizePx.y);
    float edgeFalloff = min(max(cornerRadiusPx, 6.0), minDim * 0.35);
    float edgeProximity = 1.0 - smoothstep(0.0, edgeFalloff, abs(d));
    float bendPx = min(2.0, minDim * 0.04);
    vec2 bendUv = -normal * edgeProximity * bendPx / panelSizePx;
    vec2 sampleUv = vUv + bendUv;

    vec2 texel = direction / vec2(textureSize(scratchTex, 0));
    float sigma = max(radiusPx / 3.0, 0.6);
    vec4 sum = vec4(0.0);
    float weightSum = 0.0;
    for (int i = -TAPS; i <= TAPS; i++)
    {
        float fi = float(i);
        float w = exp(-(fi * fi) / (2.0 * sigma * sigma));
        sum += texture(scratchTex, sampleUv + texel * fi) * w;
        weightSum += w;
    }
    vec4 blurred = sum / max(weightSum, 1e-5);

    // Edge-only chromatic fringing: a cheap 3-tap approximation (reads the
    // already-blurred texture at a slightly different bend magnitude per
    // channel) rather than three full reconvolutions, gated by
    // edgeProximity so the fringe only appears right at the rim -- real
    // dispersion is strongest exactly at a lens's boundary too.
    vec3 chroma = vec3(
        texture(scratchTex, sampleUv + bendUv * 1.6).r,
        texture(scratchTex, sampleUv + bendUv * 0.6).g,
        texture(scratchTex, sampleUv - bendUv * 0.6).b
    );
    vec3 backdrop = mix(blurred.rgb, chroma, edgeProximity * 0.25);

    vec3 tintedGlass = mix(backdrop, tint.rgb, tint.a);

    // Directional rim/specular: the HIG calls for "reflective rim
    // lighting" whose intensity follows the surface normal relative to a
    // fixed light direction -- brighter on the side the light comes from
    // (top-left, matching topGlow below), not a uniform ring around the
    // whole shape the way the old distance-only rim was. Narrow band (not
    // *2.5) and a lower peak -- on a small panel a wide band plus an
    // unclamped additive term was enough to wash the whole thing toward
    // white rather than reading as a thin highlight.
    vec2 lightDir = normalize(vec2(-0.55, -0.8));
    float ndotl = clamp(dot(normal, lightDir), 0.0, 1.0);
    float rimBand = 1.0 - smoothstep(0.0, borderWidthPx * 1.5, abs(d));
    float specular = pow(ndotl, 3.0) * rimBand * 0.18;

    // Steeper, lower-peak falloff than before (was pow(.,3)*0.28) -- that
    // washed out the whole top edge, worst on short panels where "top" is
    // a large fraction of the whole height.
    float topGlow = pow(clamp(1.0 - vUv.y, 0.0, 1.0), 8.0) * 0.10;
    vec3 glass = tintedGlass + vec3(topGlow + specular);

    // Shape edge, alpha cutout: this part alone (no border band) turned out
    // completely clean at the rounded corners -- confirmed live, this is
    // the thing to build back on top of. aa=1.0 matches the magnifier's own
    // circle-mask feather (features/magnifier/shaders/qrhi/mag.frag, 1.15),
    // which never had a "thick" complaint either.
    float aa = 1.0;
    float alpha = 1.0 - smoothstep(-aa, aa, d);

    // Border ring, back in the shader (a same-rasterizer, single-pass ring
    // around this same `d` -- see git history / chat: an attempt to move
    // this to a separate CPU QPainter stroke on top of the already-cropped
    // sprite, matching sli_ui_toolkit's CSD window-corner technique,
    // reintroduced visible garbage at the seam between the two independently
    // antialiased edges (the sprite's own soft alpha falloff and the
    // stroke's own QPainter-antialiased edge, computed by two different
    // rasterizers, never lined up to the sub-pixel), and insetting the
    // stroke far enough to clear that seam made the ring visibly float away
    // from the actual edge. One shader, one `d`, one antialiased edge for
    // both alpha and the ring avoids that whole class of seam by
    // construction. aaBorder/aaBorderInner back at the original proven
    // values (0.5/0.3 measured visibly *aliased* -- confirmed live: this is
    // single-sample-per-fragment rasterization, no MSAA, so a feather
    // narrower than ~1px can't represent a smooth gradient at all and just
    // aliases instead, exactly the mechanism the original comment already
    // warned about for borderWidthPx itself). Keep this at 1.0/0.5 and tune
    // *only* borderWidthPx (in glass_hud/hud.py's _refresh_backdrop) if the ring still reads too
    // heavy -- don't shrink the feather below ~1px/0.5px again.
    float aaBorder = 1.0;
    float aaBorderInner = 0.5;
    float halfBorder = borderWidthPx * 0.5;
    float outsideBorder = smoothstep(halfBorder - aaBorder, halfBorder + aaBorder, d);
    float insideBorder = smoothstep(-halfBorder - aaBorderInner, -halfBorder + aaBorderInner, d);
    float band = insideBorder * (1.0 - outsideBorder);

    vec3 color = clamp(mix(glass, borderColor.rgb, band * borderColor.a), 0.0, 1.0);

    fragColor = vec4(color * alpha, alpha);
}
