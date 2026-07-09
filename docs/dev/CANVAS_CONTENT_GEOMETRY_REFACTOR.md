# Canvas Content Geometry Refactor

Refactor plan for the "virtual canvas padding vs split-position" contract gap
found while debugging a divider misalignment on still-image export. Companion
to [QRHI_CANVAS_FEATURES.md](./QRHI_CANVAS_FEATURES.md)'s coordinate-system
rules — this doc is the concrete migration, not a new rule.

**Refactor discipline: no legacy path is kept during this migration.** Every
function this doc marks as superseded is deleted in the same commit that
wires in its replacement — not deprecated, not left behind a flag, not kept
as a fallback "in case something still needs it." If a follow-up call site is
found later, it gets migrated to the new function, it does not get the old
one un-deleted.

## Problem

Two coordinate concepts were conflated in earlier attempts at this fix:

1. **Content/canvas geometry** (feature-agnostic): given widget size, image
   size, and a `VirtualCanvasLayout` (padding requested by features like the
   magnifier or uncrop/fit-content), where do the padded canvas and the real
   image land in widget-px? This is pure geometry — it must never know what
   a "split position" or a "divider" is.
2. **Base-image-anchored split position** (feature-specific, owned by
   `viewport/zoom.py`): where does the split line sit given `split_visual`,
   zoom, pan, and a content rect? This must never re-derive canvas-bounds
   math itself — it only ever consumes rect #1's output.

A prior session (including within this one) blurred this boundary twice:

- The divider pass briefly called `resolve_frame_geometry` (concept #1)
  directly, making it the *only* consumer in the system who believed in
  live virtual-canvas padding while the base image's own live letterbox
  geometry did not — reverted.
- `shared/rendering/layout_contract.py` gained `adjust_split_position_for_canvas`
  and `resolve_overlay_clip_rect_px` — functions shaped around concept #2
  ("split position", "overlay") living inside what should be a feature-agnostic
  geometry module (concept #1). Rejected; removed in this refactor.

## Audit findings (ground truth, verified by reading code)

- `ui/canvas_infra/scene/frame_geometry.py::resolve_frame_geometry` — correct
  outer/inner rect math (accounts for `VirtualCanvasLayout` padding), **zero
  callers**. Dead code, right shape.
- `tabs/image_compare/canvas/texture_parts/base_images.py::update_letterbox_geometry`
  / `letterbox_pil` — the actual live-path function setting `state._content_rect_px`
  every frame. Computes `ratio = min(cw/img.width, ch/img.height)` directly off
  the raw image — structurally incapable of padding, never writes
  `_inner_content_rect_px`. **This is why live rendering never shows
  magnifier/uncrop virtual-canvas padding — only exports do.**
- `ui/canvas_infra/viewport/geometry.py::build_content_rect` (used by
  `viewport/zoom.py`'s `compute_zoom_display_split_position` /
  `compute_zoom_split_position_for_view_transform`, the doc-endorsed "single
  owner" of split-position math) — only takes `widget_width/height,
  image_width/height`, no virtual-canvas parameter. The canonical
  split-position formula is itself blind to padding today.
- Already correct and unaffected: **7 call sites** already implement
  `getattr(state, "_inner_content_rect_px", None) or state._content_rect_px`
  (`render_config.py:33-36,64-67`, `interaction.py:323`,
  `divider/passes.py:69`, `magnifier/plan_overlay.py:10`, `scene/builder.py:31`,
  `plan_applicator.py:96,110`). The consumer side is done — only the
  *producer* side (live path) never feeds `_inner_content_rect_px` anything
  other than "== outer".
- `zoom.py`'s split-position formulas (`base = (content_rect.y +
  content_rect.height * split_visual) / widget_height`) need **zero changes**
  — swapping in a padding-aware inner rect as `content_rect` is sufficient,
  confirmed by reading the arithmetic. No separate "adjust for canvas" step
  belongs anywhere in `zoom.py`.
- Three independent hand-rolled duplicates of "recombine split-position/clip-rect
  with padded-canvas geometry" exist:
  - `tabs/image_compare/services/gpu_export_scene.py::apply_virtual_canvas_layout_to_scene`
    (still-image export) — also mutates `scene.split_position_visual` via `replace()`.
  - `tabs/image_compare/canvas/features/magnifier/snapshot_store.py::apply_virtual_canvas_layout_to_snapshot_store`
    (video export/preview) — worse: mutates the actual `view_state.split_position_visual`
    on the snapshot store, permanently.
  - `tabs/image_compare/canvas/features/divider/commands.py::command_build_export_overlay`
    — hand-written `content_offset + content_size * split_position_visual`
    interpolation, a third copy of the same shape.
  All three mutations are redundant: `plan_applicator.py::_compute_inner_content_rect`
  already derives an equivalent `inner_split` locally and non-destructively
  from a clip rect, for both live and export paths, via the same call
  (`render_context.py:342-345,404-406`). Nothing needs `split_position_visual`
  itself ever mutated.
- `magnifier/layout_plan.py::build_magnifier_layout` is a separate,
  already-isolated pipeline (canvas-px overlay model) driven by
  `compute_canvas_plan`, not by `_content_rect_px`/`_inner_content_rect_px` —
  no double-apply risk from fixing the live path.
- `tabs/image_compare/canvas/presentation/gl_surface.py::apply_store_to_gl_canvas` —
  confirmed dead code (zero callers), same status as the old
  `resolve_frame_geometry`. Deleted in this pass.
- `tabs/image_compare/canvas/presentation/plan_builder.py::_build_snapshot_store`
  / `compute_canvas_plan` (CPU-composited still-image export pixel baking,
  `_pad_image`) — **confirmed live, not dead** (called from
  `image_export.py`, `video_snapshot_rendering.py`, `tab.py`,
  `export_context_builder.py` via `snapshot_render_plan_builder.py`). It
  already correctly funnels through `resolve_feature_virtual_layout`/
  `resolve_padding_pixels` (the primitives this refactor keeps) and bakes
  padding into output pixels rather than expressing a widget-px rect — a
  structurally different, legitimate technique for a headless render with no
  widget. It does not contain the split-position duplication bug this
  refactor targets. **Out of scope for this pass**, left untouched.

## Target design

### 1. `shared/rendering/layout_contract.py` — feature-agnostic primitives only

Keep: `NormalizedBounds`, `FeatureLayoutRequirement`, `VirtualCanvasLayout`
(+ `resolve_padding_pixels`), `resolve_virtual_canvas_layout`.

Delete: `adjust_split_position_for_canvas`, `resolve_overlay_clip_rect_px` —
no replacement lives in this module. This module answers "how much padding,
in what bounds" — never "where does a split line go" or "what is an overlay
clip rect."

### 2. One canonical content-geometry function

Rewrite `ui/canvas_infra/scene/frame_geometry.py` in place (it's dead code,
zero migration risk) to be the sole owner of "outer (padded canvas) / inner
(image-only) widget-px rect, given widget dims + image dims + an optional
`VirtualCanvasLayout`":

```python
def resolve_canvas_content_geometry(
    *, widget_width, widget_height, image_width, image_height,
    virtual_layout: VirtualCanvasLayout | None,
) -> ContentGeometry:
    ...  # virtual_layout=None -> outer == inner == plain letterbox
```

Plus `resolve_canvas_content_geometry_for_store(store, ...)` — thin wrapper
that resolves `virtual_layout` via `resolve_feature_virtual_layout` for
callers that only have a `store` (mirrors what `resolve_frame_geometry` did).

`ContentGeometry`'s rect fields keep the same shape `zoom.py` already
destructures (`.x/.y/.width/.height`) so `zoom.py`'s arithmetic needs no
changes — only its import source changes.

`viewport/geometry.py::build_content_rect` / `QuickContentRect` are deleted;
their no-padding-case math becomes `resolve_canvas_content_geometry`'s
`virtual_layout=None` branch.

### 3. Clip-rect helper (replaces the three hand-rolled duplicates)

A small feature-agnostic helper, co-located with `resolve_canvas_content_geometry`
in `frame_geometry.py`, computes "where does the inner content sit inside the
padded canvas, in canvas-px" (the same math `resolve_overlay_clip_rect_px` had,
relocated and stripped of the "overlay" name). Used by:

- Live scene build (`canvas/scene.py::build_render_scene`) — populates
  `store.runtime_cache.overlay_clip_rect` from the same `VirtualCanvasLayout`
  used for `_content_rect_px`/`_inner_content_rect_px`, if
  `apply_plan_runtime_overlays` turns out to run for the live QRhi widget too
  (verify at implementation time; see Risks).
- `gpu_export_scene.py::apply_virtual_canvas_layout_to_scene` — keeps setting
  `overlay_clip_rect`, **drops** the `adjusted_split`/`split_position_visual`
  mutation entirely.
- `magnifier/snapshot_store.py::apply_virtual_canvas_layout_to_snapshot_store` —
  keeps setting `overlay_clip_rect` (a throwaway snapshot `Store` has no live
  per-frame pass to set `_content_rect_px` for it), **drops** the
  `view_state.split_position_visual` mutation (lines ~125-131) and the now-stale
  docstring justification for it.
- `divider/commands.py::command_build_export_overlay` — replaces its
  hand-written `content_offset + content_size * split_position_visual`
  interpolation with a tiny shared `resolve_axis_position(offset, size,
  fraction)` helper (the one primitive `zoom.py` already inlines twice),
  living next to `ContentGeometry` in `viewport/geometry.py` or
  `frame_geometry.py`.

### 4. Live path becomes padding-aware

`base_images.py::update_letterbox_geometry` / `letterbox_pil` call
`resolve_canvas_content_geometry_for_store(...)` and set **both**
`state._content_rect_px = geometry.outer_rect_px` and
`state._inner_content_rect_px = geometry.inner_rect_px`. This alone, combined
with the 7 already-correct consumers, makes live rendering padding-aware.

`configure_offscreen_render`'s store-less path is left alone but should
explicitly reset `state._inner_content_rect_px = None` alongside
`state._store = None`, to avoid a stale value leaking across frames.

## Deleted in this pass (not deprecated)

- `ui/canvas_infra/scene/frame_geometry.py::resolve_frame_geometry` — superseded
  in place by `resolve_canvas_content_geometry`.
- `shared/rendering/layout_contract.py::adjust_split_position_for_canvas`,
  `resolve_overlay_clip_rect_px`.
- `ui/canvas_infra/viewport/geometry.py::build_content_rect`, `QuickContentRect`.
- `tabs/image_compare/canvas/presentation/gl_surface.py::apply_store_to_gl_canvas`
  (confirmed dead, unrelated GL-era leftover, same cleanup pass).
- The split-position-mutating halves of `gpu_export_scene.py`,
  `magnifier/snapshot_store.py`, and the hand-written interpolation in
  `divider/commands.py::command_build_export_overlay`.

## Explicitly out of scope

- `plan_builder.py::_build_snapshot_store` / `compute_canvas_plan` (CPU pixel
  baking for headless export) — live code, different technique, no
  split-position duplication bug. Separate future pass if ever unified.

## Mechanical duplication guard

A design doc didn't stop this duplication from happening once already (twice,
within this same session) — so this refactor also adds a structural test to
`tests/contracts/` (matching the existing convention there: grep/AST-based
tests that scan source rather than execute runtime code, see
`tests/contracts/_framework.py`) that fails CI the moment someone reintroduces
a fourth hand-rolled copy, rather than relying on doc review to catch it.

New file: `tests/contracts/test_canvas_content_geometry_single_owner.py`,
enforcing two rules:

1. **`VirtualCanvasLayout.canvas_bounds` / `.content_bounds` access is
   allowlisted.** Grep every `.py` file under `src/` for
   `canvas_bounds`/`content_bounds` attribute access. Only files in an
   explicit allowlist (`ui/canvas_infra/scene/frame_geometry.py`,
   `ui/canvas_infra/scene/layout_requirements.py`,
   `shared/rendering/layout_contract.py`, and their test files) may reference
   them. Any other file touching these fields directly is a new consumer
   reconstructing canvas-bounds math by hand instead of calling
   `resolve_canvas_content_geometry(_for_store)` — fail with a message
   pointing at this doc.
2. **`split_position_visual` is never combined with rect/canvas arithmetic
   outside `viewport/zoom.py`.** Grep for any file (other than
   `viewport/zoom.py`, `viewport/pipeline.py`, and their tests) that contains
   both a reference to `split_position_visual` (or `split_visual`) *and* one
   of `content_rect`, `canvas_bounds`, `content_offset`, `canvas_w`/`canvas_h`
   in a way that looks like arithmetic (a lightweight AST check: the name
   appears inside a `BinOp` alongside one of those identifiers) in the same
   function body. This is the exact shape all three deleted duplicates had
   (`gpu_export_scene.py`, `snapshot_store.py`, `divider/commands.py`) — a new
   one reintroduced anywhere should fail immediately rather than silently
   drifting from `zoom.py`'s formula.

Both checks should error with an explicit message naming this doc
(`docs/dev/CANVAS_CONTENT_GEOMETRY_REFACTOR.md`) and the one function the
violator should call instead, so the failure is actionable without needing to
re-derive the reasoning from scratch.

## Risks / accepted behavior change

- **Shipping without a feature flag, by design.** Any user with uncrop/
  fit-content or a magnifier requiring extra canvas space will now see that
  padding rendered in the live interactive canvas (previously invisible
  there, only present in exports). This is the point of the fix — live and
  export must not visually disagree — and is shipped directly, not gated.
- Confirmed: `apply_plan_runtime_overlays` does run for the live QRhi widget
  (`apply_store_to_canvas` -> `apply_canvas_render_plan` ->
  `apply_legacy_canvas_render_plan` -> `_apply_plan_full`/`_apply_plan_scene_only`
  -> `apply_plan_runtime_overlays`), so it would have clobbered the Task-4 fix's
  `_inner_content_rect_px` back to `== outer` on every resize/viewport-state
  change, since nothing populated `overlay_clip_rect` for live. Fixed in
  `plan_builder.py::build_canvas_plan`'s live-default branch (no `target_size`/
  `gl_scene` passed in by the caller): it now resolves the same
  `VirtualCanvasLayout` via `resolve_feature_virtual_layout`, expands
  `canvas_w`/`canvas_h` to the padded dimensions (matching the export path's
  convention, since `_compute_inner_content_rect`'s `sx = dw / plan.canvas_w`
  assumes `canvas_w` includes padding), sets `pad_left`/`pad_top` so the
  overlay layout call also gets padding-aware offsets, and populates
  `store.runtime_cache.overlay_clip_rect` via `resolve_canvas_clip_rect_px`
  before `build_gl_render_scene` reads it. Export/video paths already passed
  `target_size`/`gl_scene` explicitly, so this branch does not affect them.
- Confirm `widget.runtime_state._store` is populated with a real live `Store`
  by the time `upload_pil_images`/`update_letterbox_geometry` run on the
  interactive canvas (needed to call `resolve_feature_virtual_layout`).
