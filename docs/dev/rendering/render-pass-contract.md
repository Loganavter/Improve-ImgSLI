# Render Pass Contract

Render passes are retained/staged: resource lifetime and per-frame recording
are explicit, separate steps.

```python
from ui.canvas_infra.scene.pass_contract import CanvasRenderPass, SceneVisibility
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole

class MyPass(CanvasRenderPass):
    stack_role = CanvasStackRole.VIEW_ANNOTATION
    visibility = SceneVisibility.ALL

    def initialize(self, rhi, target) -> None:
        """Create persistent QRhi resources for this render target: buffers,
        shader resource bindings, the graphics pipeline. Called once per
        target lifetime (and again if the target is recreated — e.g. resize
        that invalidates the swapchain). Never create pipeline/buffer
        objects anywhere else; a pass owns its own GPU resources."""

    def should_paint(self, ctx) -> bool:
        """Cheap per-frame gate on data availability and feature-local
        presentation rules. Never export-vs-interactive policy here —
        that's `visibility`."""

    def prepare(self, widget, ctx, resource_updates) -> None:
        """Queue dynamic buffer/texture updates (uniforms, vertex data) onto
        `resource_updates`. No draw calls. Runs before the render pass is
        opened — this is where "what do I draw" gets resolved into GPU-ready
        bytes."""

    def record(self, command_buffer, widget, ctx) -> None:
        """The draw: pipeline, viewport, scissor, shader resources, vertex
        input, `command_buffer.draw(...)`. Runs inside an already-open QRhi
        render pass. This is the only place per-frame state should be
        interpreted as pixels/viewport/scissor — see
        [coordinate-systems.md](coordinate-systems.md)."""

    def release(self) -> None:
        """Destroy persistent QRhi resources. Mirror of `initialize`. A pass
        must be able to `release()` then `initialize()` again cleanly (target
        recreation, context loss)."""
```

`resolved_layer_and_priority()` resolves `stack_role` through the central
`stacking_policy.py` — a pass never computes its own ordering. Every render
pass is a `CanvasRenderPass`; there is no other pass base class.

Rules:
- mode filtering is handled centrally by the render executor
- `should_paint()` should check data availability and feature-local presentation rules, not export-vs-interactive policy
- interactive-only payloads should usually be suppressed earlier in feature `apply()`
- single-image preview is not a central render-executor flag; if a pass should be silent in that mode, it should decide that locally in `should_paint()`

Scene visibility:

| Visibility | Meaning |
|---|---|
| `SceneVisibility.INTERACTIVE` | live editing canvas only |
| `SceneVisibility.EXPORT` | export/video/offscreen rendering |
| `SceneVisibility.PREVIEW` | preview surfaces |
| `SceneVisibility.ALL` | visible in every scene mode |

Available roles:

| Role | Render Phase | Use case |
|---|---|---|
| `UNDERLAY_SPLIT` | IMAGE_DECORATION | Split/divider line |
| `IMAGE_OVERLAY_CONTENT` | IMAGE_ANNOTATION | Magnifier GPU content |
| `ANNOTATION_RING` | VIEW_ANNOTATION | Capture rings |
| `ANNOTATION_BORDER` | VIEW_ANNOTATION | Borders, occluded arcs |
| `ANNOTATION_GUIDE` | VIEW_ANNOTATION | Guide lines |
| `HUD_LABEL` | HUD | Filename overlay, status text |
| `TRANSIENT_PREVIEW` | HUD | Preview elements |
| `INTERACTION_HANDLE` | VIEW_ANNOTATION | Drag handles |
| `DEBUG_VIS` | DEBUG | Debug visualization |

Pass instances are long-lived (one per session/target). Persistent QRhi
resources (buffers, pipelines, shader resource bindings) belong on the
`CanvasRenderPass` instance, created in `initialize()` — never store them on
the widget.

## Alpha / Blending Contract

**FBO/render-target alpha must end every frame at 1.0 wherever something has
been drawn.** The base clear sets α=1. Any blend state used during the frame
must preserve that invariant.

QRhi expresses blend state via `QRhiGraphicsPipeline::TargetBlend`, which
separates color and alpha factors natively (`srcColor`/`dstColor`/`opColor`
vs `srcAlpha`/`dstAlpha`/`opAlpha`). The rule: **every pass that blends must
set `srcAlpha = One`, `dstAlpha = OneMinusSrcAlpha` explicitly** — never
leave `TargetBlend` at a default that mirrors the color factors into alpha,
which silently decays render-target alpha below 1 on every anti-aliased edge
(colored fringes on screenshot capture, invisible in the compositor). This is
a per-pipeline setting, so it's a per-`CanvasRenderPass.initialize()`
responsibility — a new pass with a default-constructed `TargetBlend` silently
reintroduces the bug.

**CPU-generated overlays uploaded as textures must be premultiplied
end-to-end.** This is a QImage/texture-format concern: premultiplied source
format in, premultiplied-aware blend factors (`One`/`OneMinusSrcAlpha` on the
color side too) on draw. Do not introduce a non-premultiplied round-trip
anywhere in that path.

If you see the symptom and don't remember why this section exists: the fix
is per-pipeline `TargetBlend` alpha factors for sticky non-premul blending,
premultiplied alpha for QImage → texture overlays. Do not paper over it with
`glColorMask`-equivalent tricks or post-pass alpha resets; fix the blending.

**Known residual case (not currently exposing the symptom, but worth
noting):** `texture_parts/upload_queue.py:queue_prepared_texture_upload`
(feeding all base-image texture uploads via `texture_parts/base_images.py`)
still does `qimage.convertToFormat(Format_RGBA8888)` (non-premul). If the
source is a `Format_ARGB32_Premultiplied` `QPixmap` with anti-aliased
transparent edges (e.g. a PNG with alpha around glyphs/icons), the
per-channel unpremul will drift R/G/B independently in the texture. The
alpha fix above keeps the render-target alpha clean, but it won't fix RGB
drift baked into the source texture itself. If that symptom appears, switch
those uploads to `Format_RGBA8888_Premultiplied` AND update the consuming
shader (main canvas + magnifier) to either unpremultiply on sample or move
to premultiplied blending for that draw — don't half-migrate.
