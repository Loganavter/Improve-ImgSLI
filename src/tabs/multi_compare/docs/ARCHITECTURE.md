# Multi Compare Architecture

## State

The tab's session state lives in `state_slots["multi_compare.state"]` — the
**single source of truth**, reduced by the core `RootReducer` exactly like
image_compare's `document` slot (registered in
`tabs/multi_compare/bootstrap_reducers.py`). MC actions dispatch through the
core `Dispatcher` (`scope="multi_compare"`), which writes the slot back to
the active session and records reference-snapshots for **undo/redo**
(`Dispatcher._UNDOABLE_TYPES`).

`MultiCompareStore` (`scene/store.py`) is a thin **facade** over the core
Dispatcher + active session slot:

- `state` reads the active session's slot;
- `dispatch(action)` forwards to the core Dispatcher;
- `subscribe(cb)` hooks core store changes (filtered to the
  `"multi_compare"` scope);
- `replace_state(state)` writes the slot directly (session restore — not a
  user action, bypasses undo).

Actions live in `tabs.multi_compare.scene.store.actions`; the pure `reduce`
in `scene/store.py` is used both by the core slot reducer and by the
standalone store mode (tests). Tree operations live in
`scene/tree_ops`; divider constraints in `scene/layout_constraints`.

`RemoveSlot`/`Clear` drop path references only — pixels live in the
tab's session-owned `pipeline/cache.py` (`MultiComparePixelCache`, keyed
`(normpath, mtime, size)`, close on evict), never in state, so undo
snapshots hold paths that re-resolve against the still-warm cache.
Decoded-tier arrivals land in the cache first, then dispatch
`NoteSlotPixels` (revision bump only, STORE replace-only) so subscribers
rebuild composition / re-sync textures. `build_composition_plan()` takes
the resolved `sources={slot_id: pixels}` alongside the state.

The `_session_harness.py` test helper fakes the narrow core slice the facade
depends on.

## Layout Model

The editable layout tree is tab-specific:

- `LeafNode` points at one slot id.
- `SplitNode` stores direction, children, and normalized split weights.
- Drop targets and divider resize operate on tree paths, not on flattened
  rendered layers.

The renderer does not consume this tree directly. `build_composition_plan()`
translates `MultiCompareState` into the shared canvas-presentation
`CompositionPlan` model:

- `CompositionPlan.canvas_w/canvas_h` are canvas-px.
- `LayerNode.rect` resolution happens before framebuffer projection.
- QRhi projection applies `sr = min(fb_w / canvas_w, fb_h / canvas_h)` once.

This separation is covered by
`tests/render/test_multi_compare_layer_contracts.py`.

## Rendering

Live rendering is owned by `MultiCompareCanvasWidget` and
`MultiCompareRhiRenderer`.

Frame flow:

1. Widget state changes through `MultiCompareStore.dispatch(...)`.
2. The widget rebuilds or reuses the active `CompositionPlan`.
3. `build_render_context(...)` projects the plan: `sr`/`ox`/`oy` for overlays,
   plus per-slot `slot_rect_uv` for the image pass.
4. `BaseImagesPass` draws each slot on a **shared fullscreen quad**; composition
   letterbox and the slot cell are applied in the fragment shader (UV), matching
   image_compare's letterbox-in-UV model. GPU tiles still use `tileRect`.
5. `GridDividersPass` draws split gaps as solid-color GPU quads (geometry from
   `DividersOverlaySource` / `ResolvedComposition.gaps`) — same idea as
   image_compare's `DividerPass`, without a framebuffer-sized overlay texture.
6. Other feature overlays (`layer_labels`, `drag_drop_overlay`) still rasterize
   into textured fullscreen quads over the image pass.

Divider and label geometry is framebuffer-pixel data derived from the
composition plan. It must not mutate composition layers or slot images.

## Export

Export uses the same composition semantics as live rendering.

`MultiCompareGpuExporter` creates an offscreen `MultiCompareCanvasWidget`,
applies a `CanvasRenderPlan` with `composition_root`, resizes the framebuffer to
the requested output size, and captures with `grabFramebuffer()`.

The composition's own canvas size remains canonical. Export output size is the
framebuffer size, not a request to rebuild the scene in a second coordinate
system.

## Coordinate Contracts

- Canvas layout uses canvas-px.
- Framebuffer output uses physical pixels.
- `sr` is the only scale between canvas-px and framebuffer pixels.
- Split gap constants are canvas-px and scale with `sr`.
- Drag/drop hit-testing that receives widget coordinates must convert through
  the same projection rules as rendering.

Tests that guard these contracts:

- `tests/render/test_multi_compare_layer_contracts.py`
- `tests/render/test_multi_compare_dividers.py`
- `tests/render/test_multi_compare_composition_builder.py`
- `tests/runtime/test_multi_compare_drop_target.py`
- `tests/runtime/test_multi_compare_divider_clamp.py`