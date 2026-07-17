# Anti-patterns & Checklist

## Anti-patterns

- Adding feature logic to `canvas_infra`
- Adding new central `if feature == ...` logic
- Duplicating state in both feature-owned storage and flat `ViewState`
- Describing the same property separately for keyframes and settings/UI
- Putting feature geometry helpers into `canvas_presentation`
- Letting write paths silently fall back to a different instance
- Treating viewport foundation as a normal editor feature
- Adding PIL/QPainter/CPU fallback render paths for QRhi features
- Recreating a central shader facade instead of feature-owned `passes.py`
- Naming infrastructure stack layers after concrete features
- Importing feature state directly from `scene.py` instead of using overrides
- Placing feature shaders under `shader_sources/`
- Storing shader programs on the widget instead of on the owning `CanvasRenderPass`
- Reintroducing executor-level special flags like `hide_in_single_preview`
- Using feature-local mode services to decide export/interactive visibility when `SceneVisibility` already expresses it
- Mixing semantic feature geometry with visual paint margins. Stroke width,
  antialiasing halos, shadows, handles, and selection outlines are render
  concerns; they must not push stored positions, hit-test anchors, guide
  endpoints, crop/capture centers, or export/layout geometry inward.
- Creating persistent QRhi resources (buffers, pipelines, shader resource
  bindings) anywhere except inside a `CanvasRenderPass`'s own
  `initialize()`/`release()` pair.
- Reasoning about device pixels / DPR anywhere before the final
  `QRhiScissor`/`QRhiViewport` construction inside `record()`.
- Reimplementing a viewport-resolved transform locally (combining
  `content_rect_px`, widget dimensions, zoom, or pan by hand) instead of
  calling the one owning formula and trusting its output.
- Rewriting semantic spit / overlay anchors on pan/zoom when ``zoom <= 1``,
  or leaving an unclamped camera rewrite in the store. Camera-anchored
  rewrite is intentional only for ``zoom > 1`` (clamped to content
  ``[0, 1]``) — see
  [investigations/divider-zoom-pan-detach.md](investigations/divider-zoom-pan-detach.md).
- Clamping a display mapping to `[0, 1]` when the point can leave the
  widget at zoom-out.
- Clipping a camera-moved overlay with the fit-zoom `content_rect_px` via
  live QRhi content scissor (or assuming magnifier correctness proves that
  path — live magnifier often skips content scissor).
- Using screen `vTexCoord` spit for geometry that belongs in letterboxed
  image UV / local overlay UV (magnifier model).
- Leaving a pipeline's `TargetBlend` alpha factors at a default that mirrors
  the color factors, instead of setting `srcAlpha = One` /
  `dstAlpha = OneMinusSrcAlpha` explicitly.
- Mixing the "canvas-px overlay" coordinate model with the "full-widget
  base-image-anchored" model for the same piece of geometry — decide which
  one a feature's geometry belongs to and stay in that space end to end.
- Building a `QRhiScissor`/`QRhiViewport` by hand instead of calling
  `resolve_rhi_scissor`, or deciding its Y-flip from `isYUpInFramebuffer()`
  alone without also checking `WA_DontShowOnScreen` — see
  [coordinate-systems.md](coordinate-systems.md).
- Doing per-frame CPU work in `prepare()` that belongs in `initialize()`
  (recomputing something that doesn't change between frames), or doing
  resource creation in `record()` that belongs in `initialize()`.
- Letting a feature file grow past ~400 lines without either splitting it
  or adding a `File-Size-Exempt:` docstring line explaining why it can't be
  split further (see `tests/contracts/test_canvas_features_file_size.py`).
  The other structural contracts here (manifest exports, `RENDER_PASSES`,
  `stack_role`, ...) are all satisfiable by one oversized file that mixes
  unrelated responsibilities — this rule exists to keep that from becoming
  the default.

## Checklist

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
      alone — see [investigations/divider-zoom-pan-detach.md](investigations/divider-zoom-pan-detach.md)
- [ ] Overlay-style geometry stays in canvas-px end to end; base-image-
      anchored geometry stays in its declared space end to end — not mixed
- [ ] Blend pipeline sets `TargetBlend` alpha factors explicitly
      (`srcAlpha = One`, `dstAlpha = OneMinusSrcAlpha`) if it blends at all
- [ ] `RENDER_PASSES` exported from the feature's own `passes.py` — nothing
      hand-wired into a central registry
- [ ] No new shader source files under `shader_sources/` — feature shaders
      live under the feature's own folder
- [ ] No file over ~400 lines without a `File-Size-Exempt:` justification
