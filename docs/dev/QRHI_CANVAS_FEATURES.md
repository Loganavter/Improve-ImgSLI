# QRhi Canvas Features Architecture

Target-state companion to [CANVAS_FEATURES.md](./CANVAS_FEATURES.md) (the
pre-migration raw-OpenGL model). This is not a survey of what the code
currently does — it's what the QRhi architecture **should** guarantee. The
line-by-line audit against this doc is a separate, later step.

**Core idea, unchanged from the GL era**: a feature doesn't handle zoom, pan,
coordinate transforms, raw Qt events, or serialization — the infrastructure
does. See [Feature Isolation Model](./CONTRACTS.md#feature-isolation-model-the-abstraction).

## What changed vs the GL era, and what didn't

Backend-agnostic layers (Python-level: reducers, store, scene graph, gesture
routing, properties) carry over **unchanged in concept** — they never talked
to GL directly and don't need to talk to QRhi directly either:

- `CanvasWidgetFeature` / `CanvasSceneFeature` contracts and their fields.
- `CanvasFeatureProperty` schema.
- Command aliases.
- Gesture bindings.
- Viewport Change Contract.
- Canvas Layout Contract (virtual canvas union of normalized bounds).
- Scene Pipeline (build / apply / hit-test).
- Keyframing rules.
- Source-of-truth rules (feature-owned state, no silent fallback writes).

What changed is everything that used to assume "the renderer issues
immediate-mode GL calls": the render pass contract, how persistent GPU
resources are owned, how blending is expressed, and — the one that actually
bites — **one of the coordinate systems gained a genuinely different shape**,
not just a different file to read it from.

## Package Structure (QRhi feature)

```
src/tabs/<tab>/canvas/features/<name>/
  __init__.py
  manifest.py          # exports FEATURE / WIDGET_FEATURE — same role as before
  passes.py             # RENDER_PASSES: list[CanvasRenderPass] — QRhi passes
  feature.py             # CanvasSceneFeature, if scene-participating
  widget.py              # CanvasWidgetFeature definition
  state.py               # feature-local state helpers
  properties.py          # CanvasFeatureProperty schema
  actions.py / commands.py / events.py / gestures.py / interaction.py
  runtime_hooks.py        # render-scene override / runtime payload helpers
  settings_bindings.py
  toolbar.py
  shaders/                # .vert/.frag sources + compiled .qsb, feature-owned
```

Feature ownership moved from global (`src/ui/canvas_features/<name>/`) to
per-tab (`src/tabs/<tab>/canvas/features/<name>/`) — a tab owns its own
feature set instead of every feature being visible to every tab by default.
`canvas_infra` (`scene/`, `viewport/`, `stacking_policy.py`, the pass/feature
contracts) does **not** move per-tab — it stays a shared library under
`src/ui/canvas_infra/`, imported the same way by every tab (see the
`from ui.canvas_infra.scene.pass_contract import ...` example below). Only
concrete features are tab-owned; infrastructure is not.

### Auto-Discovery

| Registry | Looks for | In module |
|---|---|---|
| `widget_registry` | `WIDGET_FEATURE: CanvasWidgetFeature` | `manifest.py` or `widget.py` |
| `feature_registry` | `FEATURE: CanvasSceneFeature` | `manifest.py` or `feature.py` |
| `pass_registry` (QRhi) | `RENDER_PASSES: list[CanvasRenderPass]` | `passes.py` |

Same principle as the GL era: never hand-wire a pass into a central file.
Export it from your feature's `passes.py` and it's discovered.

## The Render Pass Contract (QRhi)

The GL era was immediate-mode: one `paint(widget, ctx)` call did setup and
draw in the same breath, every frame. QRhi is retained/staged — resource
lifetime and per-frame recording are explicitly separate steps:

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
        objects anywhere else; a pass owns its own GPU resources, the same
        way a GL-era pass owned its `QOpenGLShaderProgram`."""

    def should_paint(self, ctx) -> bool:
        """Unchanged in role from the GL era: cheap per-frame gate on data
        availability and feature-local presentation rules. Never
        export-vs-interactive policy here — that's `visibility`."""

    def prepare(self, widget, ctx, resource_updates) -> None:
        """Queue dynamic buffer/texture updates (uniforms, vertex data) onto
        `resource_updates`. No draw calls. Runs before the render pass is
        opened — this is where "what do I draw" gets resolved into GPU-ready
        bytes."""

    def record(self, command_buffer, widget, ctx) -> None:
        """The draw: pipeline, viewport, scissor, shader resources, vertex
        input, `command_buffer.draw(...)`. Runs inside an already-open QRhi
        render pass. This is the only place per-frame state should be
        interpreted as pixels/viewport/scissor — see Coordinate Systems."""

    def release(self) -> None:
        """Destroy persistent QRhi resources. Mirror of `initialize`. A pass
        must be able to `release()` then `initialize()` again cleanly (target
        recreation, context loss)."""
```

`resolved_layer_and_priority()` still resolves `stack_role` through the
central `stacking_policy.py` exactly as before — a pass never computes its
own ordering, and the same table drives both the legacy `CanvasGLRenderPass`
and the new `CanvasRenderPass` during migration.

`SceneVisibility` (`INTERACTIVE` / `EXPORT` / `PREVIEW` / `ALL`) is unchanged.

## Rendering Model

Still one renderer backend, still two state-preparation paths — this is a
concept, not an implementation detail, and it survives the migration intact:

- **Live authoring path** — the interactive canvas reads live `Store`/
  `ViewState`/feature state every frame. The only path a user's drag,
  toolbar click, or shortcut should ever mutate.
- **Snapshot replay path** — preview, image export, video preview/export,
  thumbnails build a frozen snapshot, turn it into a render plan, and feed
  that plan through the *same* passes. No parallel rendering logic for "what
  export looks like."

**Rule, unchanged:** a fix that only works in export/preview/video code with
no live-canvas counterpart is the wrong fix. It will drift the first time the
live path changes underneath it.

QRhi makes the distinction between modes an explicit `mode` value
(`"interactive"` / `"preview"` / `"export"`) passed into render-context
construction. That's a convenience for expressing `SceneVisibility` decisions
— it is not license to sprinkle `if mode == "export"` branches inside a pass.

## Coordinate Systems

This is the section that actually changed shape, so it gets the most
scrutiny.

### The foundation: normalized `0.0–1.0` base-image space, and how uncrop/crop fits into it

Underneath both models below sits one canonical, resolution-independent
space: base comparison content occupies `x=0.0..1.0`, `y=0.0..1.0` in
normalized base-image coordinates — this is the Canvas Layout Contract's
model. A feature that needs canvas space beyond the image itself (a
magnifier that can pan past the edge, say) declares a `FeatureLayoutRequirement`
in this same normalized space — e.g. `x=0.4..1.5` — and the layout resolver
unions every feature's requirement with the base `0..1` rect into a
`VirtualCanvasLayout`. **Canvas-px, as used throughout this doc, is that
resolved union — not a fixed image-sized rect.** When a feature asks for
extra room, canvas-px grows to include it; `sr` (the canvas-px → widget-px
scale) is computed against the *grown* canvas, not the raw image size.

This is exactly the mechanism uncrop/crop (fit-content padding) rides on:

- **Crop mode**: the visible content is clipped to fit the output aspect —
  no extra canvas space needed, `content_rect_px` in the widget is the whole
  story, and it equals the letterboxed image rect.
- **Uncrop / fit-content mode**: instead of clipping, padding is added around
  the image so nothing is cut off when the output aspect doesn't match the
  image aspect. That padding is exactly a `FeatureLayoutRequirement`-shaped
  extension of the virtual canvas beyond `0..1` — the resolved canvas is
  *larger* than the raw image, filled with the configured fill color outside
  the image's own bounds.

Because of this, there are **two different "content rects" in play** once
uncrop/fit-content padding is active, and features must be deliberate about
which one their geometry means:

- `_content_rect_px` — the full resolved canvas rect within the widget,
  *including* any uncrop padding. This is "where the whole virtual canvas
  landed," not "where the image is."
- `_inner_content_rect_px` — the semantic rect of just the image itself,
  inside that padded canvas, when fit-content padding is active. This is
  "where the image is," and it's what should be used whenever a feature
  means "the edge of the actual picture," not "the edge of the padded
  canvas."

The rule (same one already stated for semantic geometry vs paint extents):
**read `_inner_content_rect_px` when it's set, fall back to
`_content_rect_px` otherwise** — never assume `_content_rect_px` is the image
bounds, because under uncrop it isn't. A feature that hit-tests, clamps, or
anchors against `_content_rect_px` unconditionally will silently drift onto
the padding the moment a user enables fit-content/uncrop, in exactly the
"invisible at the common case, wrong at the edge case" shape that makes this
class of bug hard to catch in a quick smoke test.

### The GL-era model, and why it still works for overlays

The old model: image-px → canvas-px (an internal logical render target,
independent of actual widget size) → widget-px, with exactly **one**
conversion step (`sr = min(widget_w/canvas_w, widget_h/canvas_h)`) owned by
the runtime. Every feature-owned overlay (magnifier center, capture rect,
guide endpoint) stores canvas-px and never computes `sr` itself.

This model is not obsolete — it's still correct for geometry that exists
**independently of the base image's own split/letterbox rendering**. An
overlay's job is "be at this semantic point on the image, at whatever zoom
the base image happens to be rendered at." Canvas-px plus one owned
conversion step still expresses that correctly and should keep doing so.

### The part that's new: base-image-anchored geometry

The base-image split/letterbox path never had a separate offscreen render
target to convert *from* in the QRhi model — it resolves directly against
the widget's own render target, in **full-widget-fraction** space (`[0, 1]`
across the *whole widget*, not the letterboxed content rect), because that's
the space the shader's `vTexCoord` and `splitPosition` uniform live in.

This is a second, structurally different space, and it exists for a
legitimate reason: the shader has no concept of "canvas-px" — it only knows
the widget's own UV space. Any pass whose geometry is defined **relative to
the split line or the letterboxed image itself** (not an independent
overlay) needs to end up in this same space to stay visually locked to what
the shader draws.

### The one rule that matters more than the table

Both models above share a design principle, and it's the same principle the
GL-era doc already stated for canvas-px: **there is exactly one function
that resolves a semantic position into "where to draw," and every consumer
must call that function — never reconstruct the transform locally by
combining primitives by hand.**

- For overlay geometry: call the existing canvas-px → widget-px conversion.
  Don't hand-roll `sr`.
- For base-image-anchored geometry: call the viewport-layer formula
  (`get_display_split_position` / `compute_display_split_position` /
  `compute_zoom_split_position_for_view_transform`) and treat its output as
  **already fully resolved** — already widget-normalized, already
  letterbox-aware, already zoom/pan-aware. Do not take that output and
  combine it *again* with `content_rect_px`, widget dimensions, or zoom by
  hand "just to be sure." If the formula didn't already do what you need,
  the fix belongs inside the formula (one owner), not layered on top of its
  output (two owners silently disagreeing).

Violating this rule looks identical in both models: correct-looking code
that's subtly wrong by an amount proportional to distance from some neutral
point (center, zoom=1, pan=0) — because a transform got applied twice, once
inside the formula and once again by the caller.

### The two remaining spaces (bookkeeping, not authoring)

- **`content_rect_px`** (widget-px rect of the letterboxed image within the
  widget) is CPU-side bookkeeping: clip rects, scissors, hit-testing. It is
  an *output* consumed to constrain drawing, never an *input* for re-deriving
  a value that a viewport formula already resolved.
- **Device/framebuffer-px** (widget-px × device pixel ratio) exists only at
  the final `QRhiScissor` / `QRhiViewport` construction, inside `record()`.
  Nothing upstream of that last conversion should think in device pixels —
  if a pass's `prepare()` step is reasoning about DPR, that's a sign the
  concern leaked one layer too early.

### `isYUpInFramebuffer()` is not the whole Y-flip story for offscreen widgets

`resolve_rhi_scissor()` (`tabs/image_compare/canvas/rhi_feature_common.py`)
flips a scissor's Y when `rhi.isYUpInFramebuffer()` is true — correct for a
widget that eventually gets composited on screen. But `QRhiWidget` always
renders into a backing texture regardless of visibility; a **visible**
widget goes through an extra compositing step (its backing texture is
drawn into the top-level window, e.g. via `QPainter`) that silently absorbs
the backend's Y convention. A widget that is never shown — created with
`Qt.WidgetAttribute.WA_DontShowOnScreen` purely to call `grabFramebuffer()`
on it (the GPU export/preview canvas, `gpu_export_canvas` in
`plugins/export/services/gpu_export_proxy.py`) — never runs that
compositing step, so the raw scissor Y must be flipped by hand even when
`isYUpInFramebuffer()` reports `false` for that same RHI backend.

Symptom this produces if missed: a scissor-clipped pass (in practice,
`DividerPass`) renders with the *correct height* but the *wrong offset* —
shifted by exactly `framebuffer_height - 2*content_y - content_height`,
i.e. it looks like it's anchored to the wrong edge — while anything drawn
via direct vertex/UV geometry (the base image) is unaffected, because it
never goes through a scissor rect at all. This is easy to misdiagnose as a
`content_rect_px`/`_inner_content_rect_px`/split-position bug (see
[UNCROP_FIT_CONTENT_AUDIT.md](./UNCROP_FIT_CONTENT_AUDIT.md)'s now-corrected
"Проблема с Y у divider" section) because every geometry log along the way
reports numerically correct values — the bug is downstream of all of them,
at the point the scissor is actually consumed by the backend.

Fix in place: `resolve_rhi_scissor` flips when `y_up OR
widget.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)`, not `y_up`
alone. Any future pass or helper that builds its own `QRhiScissor`/
`QRhiViewport` by hand (instead of calling `resolve_rhi_scissor`) must
apply the same rule, or route through that function instead of
reimplementing it.

### Target rule of thumb

Before combining a viewport-resolved value with `content_rect_px`, widget
dimensions, or zoom "by hand," ask: did this value already come out of a
viewport-formula function? If yes, it's already resolved — treat it as an
opaque final answer, not a raw ingredient.

## Alpha / Blending Contract (QRhi)

The GL-era invariant is unchanged in intent, different in API surface:

**FBO/render-target alpha must end every frame at 1.0 wherever something has
been drawn.** The base clear still sets α=1. Any blend state used during the
frame must preserve that invariant.

The GL era expressed the fix as `glBlendFuncSeparate(GL_SRC_ALPHA,
GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA)` — separate color and
alpha blend factors, because plain `glBlendFunc` applies the *color* factors
to the alpha channel too and decays it below 1 on every AA edge.

QRhi's equivalent is `QRhiGraphicsPipeline::TargetBlend`, which already
separates color and alpha factors natively (`srcColor`/`dstColor`/`opColor`
vs `srcAlpha`/`dstAlpha`/`opAlpha`). The target rule: **every pass that
blends must set `srcAlpha = One`, `dstAlpha = OneMinusSrcAlpha` explicitly**
— never leave `TargetBlend` at a default that mirrors the color factors into
alpha, which reproduces the exact GL-era bug (colored fringes on screenshot
capture, invisible in the compositor). This is a per-pipeline setting, so
it's a per-`CanvasRenderPass.initialize()` responsibility, not a
once-per-process sticky state like the old `glBlendFuncSeparate` call — a new
pass with a default-constructed `TargetBlend` silently reintroduces the bug.

**CPU-generated overlays uploaded as textures must be premultiplied
end-to-end.** This half of the contract is backend-agnostic — it's a QImage/
texture-format concern, not a GL-vs-QRhi concern — and carries over verbatim:
premultiplied source format in, premultiplied-aware blend factors
(`One`/`OneMinusSrcAlpha` on the color side too) on draw. Do not introduce a
non-premultiplied round-trip anywhere in that path.

## Everything backend-agnostic, restated briefly

These don't change shape under QRhi; they're listed here so this doc is
self-sufficient as the target-state reference, not because they need new
rules:

- **Viewport Change Contract** — feature commands that mutate state affecting
  rendering must call `emit_viewport_change()`. Still true; still nothing to
  do with which renderer backend is active.
- **Gesture Bindings** — features declare `build_gesture_bindings`; shared
  event code never branches on feature identity. Still true.
- **Command Aliases** — shared code resolves capabilities via
  `get_canvas_feature_command_by_alias`, never a direct feature-name lookup.
  Still true.
- **Canvas Layout Contract** — features report normalized base-image bounds;
  a layout resolver unions them into a virtual canvas; viewport transform
  applies zoom/pan/output sizing afterward. Still true, and notably: this is
  a *third* semantic model, deliberately separate from both coordinate
  systems above — a feature declaring layout requirements is not the same
  as a feature drawing base-image-anchored geometry, don't conflate them.
- **Runtime cache vs reducible state** — anything derived from actions lives
  in reducible state; anything written as a side effect of a successful
  frame lives in the runtime cache, outside the reducer pipeline. Still true,
  and matters just as much for QRhi resource-readiness flags as it did for GL
  texture-identity hashes.
- **Semantic geometry vs paint extents** — stroke width, AA fringe, shadow
  blur are render concerns; they must never leak into stored positions,
  hit-test anchors, or clamp margins. Still true.
- **Keyframing rules**, **Source-of-truth rules**, **Scene Pipeline** — no
  QRhi-specific change; see the GL-era doc for the full statement of each.
- **Pan-at-zoom-≤1 invariant** — at `zoom <= 1.0`, pan must always be `(0, 0)`.
  When the image fully fits the widget, panning has no meaning; a non-zero pan
  at `zoom <= 1.0` desyncs the shader (which always uses raw pan) from overlay
  formulas (which treat pan as zero at this zoom) — the image moves, overlays
  don't, overlays visually "fly away." Enforced at the source in
  `compute_zoom_wheel_transform` / `compute_zoom_pan_drag_transform`
  (`src/ui/canvas_infra/viewport/zoom.py`). Any new pass or feature that
  computes its own pan-like transform (for either coordinate model above) must
  clamp pan the same way at the source — never read pan at `zoom <= 1.0` and
  try to interpolate or "smooth" across the boundary; treat it as guaranteed
  zero instead.
- **Split-position dual-mode behavior** — the split line has two distinct
  anchoring modes tied to the same invariant: at `zoom > 1.0` it's
  camera-anchored (store `split_position` recomputes as zoom/pan change to
  keep the visual position fixed on screen —
  `compute_zoom_split_position_for_view_transform`); at `zoom <= 1.0` it's
  image-anchored (store value unchanged, pan is zero by the invariant above —
  `compute_zoom_display_split_position`). Any new base-image-anchored pass
  with similar "where on the image am I" semantics should follow the same
  split at `zoom == 1.0`, not invent a third behavior.

## Anti-patterns (QRhi-specific, additive to the GL-era list)

- Creating persistent QRhi resources (buffers, pipelines, shader resource
  bindings) anywhere except inside a `CanvasRenderPass`'s own
  `initialize()`/`release()` pair.
- Reasoning about device pixels / DPR anywhere before the final
  `QRhiScissor`/`QRhiViewport` construction inside `record()`.
- Reimplementing a viewport-resolved transform locally (combining
  `content_rect_px`, widget dimensions, zoom, or pan by hand) instead of
  calling the one owning formula and trusting its output.
- Leaving a pipeline's `TargetBlend` alpha factors at a default that mirrors
  the color factors, instead of setting `srcAlpha = One` /
  `dstAlpha = OneMinusSrcAlpha` explicitly.
- Mixing the "canvas-px overlay" coordinate model with the "full-widget
  base-image-anchored" model for the same piece of geometry — decide which
  one a feature's geometry belongs to and stay in that space end to end.
- Building a `QRhiScissor`/`QRhiViewport` by hand instead of calling
  `resolve_rhi_scissor`, or deciding its Y-flip from `isYUpInFramebuffer()`
  alone without also checking `WA_DontShowOnScreen` — see "Coordinate
  Systems" above.
- Doing per-frame CPU work in `prepare()` that belongs in `initialize()`
  (recomputing something that doesn't change between frames), or doing
  resource creation in `record()` that belongs in `initialize()`.

## Checklist (QRhi-specific, additive to the GL-era checklist)

- [ ] Persistent GPU resources created in `initialize()`, destroyed in
      `release()` — nothing created in `prepare()` or `record()`
- [ ] `record()` is the only place device-pixel/DPR conversion happens
- [ ] Any position derived from a viewport-formula function is treated as
      final — not recombined with `content_rect_px`/widget dims/zoom
- [ ] Overlay-style geometry stays in canvas-px end to end; base-image-
      anchored geometry stays in full-widget-fraction end to end — not mixed
- [ ] Blend pipeline sets `TargetBlend` alpha factors explicitly
      (`srcAlpha = One`, `dstAlpha = OneMinusSrcAlpha`) if it blends at all
- [ ] `RENDER_PASSES` exported from the feature's own `passes.py` — nothing
      hand-wired into a central registry

## Next step

This doc states the target model. It does not yet claim the current
codebase fully complies with it — most notably, whether every base-image-
anchored pass correctly treats viewport-formula output as final, and whether
every pipeline sets its alpha blend factors explicitly rather than relying on
defaults. That line-by-line audit against this doc is the next, separate
pass.
