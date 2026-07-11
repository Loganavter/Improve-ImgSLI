# Coordinate Systems

This section covers the coordinate spaces canvas features work in, and the
one rule for combining them correctly.

## The foundation: normalized `0.0–1.0` base-image space, and how uncrop/crop fits into it

Underneath both models below sits one canonical, resolution-independent
space: base comparison content occupies `x=0.0..1.0`, `y=0.0..1.0` in
normalized base-image coordinates — this is the Canvas Layout Contract's
model (see [contracts.md](contracts.md#canvas-layout-contract)). A feature
that needs canvas space beyond the image itself (a magnifier that can pan
past the edge, say) declares a `FeatureLayoutRequirement` in this same
normalized space — e.g. `x=0.4..1.5` — and the layout resolver unions every
feature's requirement with the base `0..1` rect into a `VirtualCanvasLayout`.
**Canvas-px, as used throughout this doc, is that resolved union — not a
fixed image-sized rect.** When a feature asks for extra room, canvas-px
grows to include it; `sr` (the canvas-px → widget-px scale) is computed
against the *grown* canvas, not the raw image size.

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

The rule (same one already stated for semantic geometry vs paint extents in
[zoom-pan.md](zoom-pan.md#semantic-geometry-vs-paint-extents)):
**read `_inner_content_rect_px` when it's set, fall back to
`_content_rect_px` otherwise** — never assume `_content_rect_px` is the image
bounds, because under uncrop it isn't. A feature that hit-tests, clamps, or
anchors against `_content_rect_px` unconditionally will silently drift onto
the padding the moment a user enables fit-content/uncrop, in exactly the
"invisible at the common case, wrong at the edge case" shape that makes this
class of bug hard to catch in a quick smoke test.

### Single resolver for both rects: `resolve_canvas_content_geometry`

Both rects above come from exactly one function,
`ui/canvas_infra/scene/frame_geometry.py::resolve_canvas_content_geometry`
(plus its store-driven wrapper, `resolve_canvas_content_geometry_for_store`),
returning a `ContentGeometry` with `outer_rect_px` (== `_content_rect_px`) and
`inner_rect_px` (== `_inner_content_rect_px`). It takes widget dims, image
dims, and an optional `VirtualCanvasLayout`; with `virtual_layout=None` (or a
unit-bounds layout) `outer_rect == inner_rect`, i.e. the plain letterbox case.
The `VirtualCanvasLayout` itself comes from the one other resolver in this
chain, `ui/canvas_infra/scene/layout_requirements.py::resolve_feature_virtual_layout`,
which unions every registered `render.layout_requirement` command
feature-agnostically (it has no knowledge of the magnifier, divider, or any
other specific feature).

This single-owner chain is wired into **both** the live authoring path and
the snapshot replay path (still-image export, video export/preview): the
live canvas's per-frame letterbox step
(`tabs/image_compare/canvas/texture_parts/base_images.py::update_letterbox_geometry`)
calls `resolve_canvas_content_geometry_for_store` every frame — not only on
image change — so a feature's padding requirement changing (e.g. the
magnifier needing more room this frame) is reflected immediately, with no
stale-geometry window. Live rendering therefore shows uncrop/fit-content and
magnifier-overflow padding the same way exports do. `gpu_export_scene.py::apply_virtual_canvas_layout_to_scene`,
`magnifier/snapshot_store.py::apply_virtual_canvas_layout_to_snapshot_store`,
and `divider/commands.py::command_build_export_overlay` all call this same
resolver rather than recombining split position and padded-canvas geometry by
hand, and none of them mutate `split_position_visual` as a side effect.

A structural contract test, `tests/contracts/test_canvas_content_geometry_single_owner.py`,
enforces this stays a single owner going forward: it greps `src/` for direct
`VirtualCanvasLayout.canvas_bounds`/`.content_bounds` access outside an
explicit allowlist (`frame_geometry.py`, `layout_requirements.py`,
`shared/rendering/layout_contract.py`, and their tests), and separately flags
any file outside `viewport/zoom.py`/`viewport/pipeline.py` that combines
`split_position_visual` with rect/canvas arithmetic in the same function body
— the exact shape all three deleted duplicates had. A new hand-rolled copy of
either fails CI immediately instead of silently drifting.

## Canvas-px overlay model

Overlay geometry (magnifier center, capture rect, guide endpoint) uses
image-px → canvas-px (an internal logical space, independent of actual
widget size) → widget-px, with exactly **one** conversion step
(`sr = min(widget_w/canvas_w, widget_h/canvas_h)`) owned by the runtime.
Every feature-owned overlay stores canvas-px and never computes `sr` itself.

This model is correct for geometry that exists **independently of the base
image's own split/letterbox rendering**. An overlay's job is "be at this
semantic point on the image, at whatever zoom the base image happens to be
rendered at." Canvas-px plus one owned conversion step expresses that
correctly.

## Base-image-anchored geometry

The base-image split/letterbox path resolves directly against the widget's
own render target, in **full-widget-fraction** space (`[0, 1]` across the
*whole widget*, not the letterboxed content rect), because that's the space
the shader's `vTexCoord` and `splitPosition` uniform live in.

This is a second, structurally different space from the canvas-px model
above, and it exists for a legitimate reason: the shader has no concept of
"canvas-px" — it only knows the widget's own UV space. Any pass whose
geometry is defined **relative to the split line or the letterboxed image
itself** (not an independent overlay) needs to end up in this same space to
stay visually locked to what the shader draws.

## The one rule that matters more than the table

Both models above share one design principle: **there is exactly one
function that resolves a semantic position into "where to draw," and every
consumer must call that function — never reconstruct the transform locally
by combining primitives by hand.**

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

## The two remaining spaces (bookkeeping, not authoring)

- **`content_rect_px`** (widget-px rect of the letterboxed image within the
  widget) is CPU-side bookkeeping: clip rects, scissors, hit-testing. It is
  an *output* consumed to constrain drawing, never an *input* for re-deriving
  a value that a viewport formula already resolved. All known consumers that
  clamp/hit-test/derive split-position off this rect already apply the
  `_inner_content_rect_px` fallback rule stated above
  (`render_config.py`, `interaction.py`, `divider/passes.py`,
  `magnifier/plan_overlay.py`, `scene/builder.py`, `plan_applicator.py`).
- **Device/framebuffer-px** (widget-px × device pixel ratio) exists only at
  the final `QRhiScissor` / `QRhiViewport` construction, inside `record()`.
  Nothing upstream of that last conversion should think in device pixels —
  if a pass's `prepare()` step is reasoning about DPR, that's a sign the
  concern leaked one layer too early.

## `isYUpInFramebuffer()` is not the whole Y-flip story for offscreen widgets

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
`content_rect_px`/`_inner_content_rect_px`/split-position bug — a real
instance of this misdiagnosis cost a full debugging pass: detailed log
tracing of `resolve_rhi_scissor`/`_resolve_divider_state` confirmed
`content_rect_px`, `display_split`, `position_px` and the computed scissor
were all numerically correct on every frame, and the actual bug was purely
in how the GPU backend consumed that already-correct scissor. Every geometry
log along the way reports numerically correct values — the bug is downstream
of all of them, at the point the scissor is actually consumed by the
backend.

Fix in place: `resolve_rhi_scissor` flips when `y_up OR
widget.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)`, not `y_up`
alone. Any future pass or helper that builds its own `QRhiScissor`/
`QRhiViewport` by hand (instead of calling `resolve_rhi_scissor`) must
apply the same rule, or route through that function instead of
reimplementing it.

## Target rule of thumb

Before combining a viewport-resolved value with `content_rect_px`, widget
dimensions, or zoom "by hand," ask: did this value already come out of a
viewport-formula function? If yes, it's already resolved — treat it as an
opaque final answer, not a raw ingredient.
