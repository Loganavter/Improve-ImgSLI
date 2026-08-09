# Pre-merge checklist

Tick list only. For the prose rules (patterns / anti-patterns) see
`docs/dev/rendering/patterns.md`, and for QRhi / Wayland / scissor case
narratives see `docs/dev/rendering/qrhi-gotchas.md` — both in the private
`improve-imgsli-internal-docs` repo (not in this repo).

Before merging a new canvas feature:

- [ ] Package in `src/tabs/<tab>/canvas/features/<name>/`
- [ ] `manifest.py` exports `WIDGET_FEATURE` (and optionally `FEATURE`)
- [ ] `name` field is unique and does not start with `_`
- [ ] Reducers are no-op if feature has no state actions
- [ ] Commands exposed via aliases (not direct feature-name lookups)
- [ ] **All state-modifying commands emit viewport changes** (see [Viewport Change Contract](zoom-pan.md#viewport-change-contract))
- [ ] Render passes use `stack_role`, not hardcoded `layer`/`priority`
- [ ] Render passes set `visibility` explicitly
- [ ] Scene z_order uses `stack_role` via `CanvasFeatureZOrder`
- [ ] No imports of this feature in shared `ui/`, `events/`, or `plugins/` code
- [ ] Mouse gestures declared via `build_gesture_bindings`, not added to `mouse.py`
- [ ] Host context-menu exclusions declared via `build_context_menu_zones`, not hard-coded in the canvas widget
- [ ] User-editable values declared as `CanvasFeatureProperty`
- [ ] No central registry file was edited
- [ ] Feature-specific helpers not in `canvas_presentation`
- [ ] Persistent GPU resources created in `initialize()`, destroyed in
      `release()` — nothing created in `prepare()` or `record()`
- [ ] `record()` is the only place device-pixel/DPR conversion happens
- [ ] Any position derived from a viewport-formula function is treated as
      final — not recombined with `content_rect_px`/widget dims/zoom
- [ ] Semantic spit / camera-locked overlays stay in content space; paint
      that must follow the zoomed image uses
      `map_content_rect_through_view` (or equivalent), not fit-zoom scissor
      alone — see `src/tabs/image_compare/docs/investigations/divider-zoom-pan-detach.md`
      in `improve-imgsli-internal-docs` (private, not in this repo)
- [ ] Overlay-style geometry stays in canvas-px end to end; base-image-
      anchored geometry stays in its declared space end to end — not mixed
- [ ] Blend pipeline sets `TargetBlend` alpha factors explicitly
      (`srcAlpha = One`, `dstAlpha = OneMinusSrcAlpha`) if it blends at all
- [ ] `RENDER_PASSES` exported from the feature's own `passes.py` — nothing
      hand-wired into a central registry
- [ ] No new shader source files under `shader_sources/` — feature shaders
      live under the feature's own folder
- [ ] No file over ~400 lines without a `File-Size-Exempt:` justification
- [ ] Scissors go through `resolve_rhi_scissor` (offscreen Y-flip included) —
      see "Offscreen scissor Y-flip" in `docs/dev/rendering/qrhi-gotchas.md`
      (`improve-imgsli-internal-docs`, private)
- [ ] No QWidget autofill on `QRhiWidget`
      (see "QRhiWidget autofill" in `docs/dev/rendering/qrhi-gotchas.md`,
      `improve-imgsli-internal-docs`, private)
