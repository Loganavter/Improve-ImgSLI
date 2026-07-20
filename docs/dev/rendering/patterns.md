# Rendering patterns & anti-patterns

Short rules for live canvas / export / snapshot work. **No case narratives
here** — only the rule and a link to the detailed write-up when one exists.

| Need | Doc |
|---|---|
| Coordinate spaces / single-resolver | [coordinate-systems.md](coordinate-systems.md) |
| Pass lifecycle / blend / stack roles | [render-pass-contract.md](render-pass-contract.md) |
| Zoom/pan / semantic vs paint | [zoom-pan.md](zoom-pan.md) |
| QRhi / Wayland / scissor / compositing surprises | [qrhi-gotchas.md](qrhi-gotchas.md) |
| Full investigation write-ups | [investigations/](investigations/) |
| Pre-merge tick list | [checklist.md](checklist.md) |

---

## Patterns (do this)

### Architecture

- Keep feature logic in `src/tabs/<tab>/canvas/features/<name>/`; infrastructure
  stays generic (`canvas_infra`, presentation helpers).
- Own GPU resources on the `CanvasRenderPass`: create in `initialize()`,
  destroy in `release()`, draw in `record()`.
- Export `RENDER_PASSES` / `WIDGET_FEATURE` from the feature package — no
  hand-wiring into a central registry.
- Keep live, export preview, final export, and video snapshots visually
  consistent on purpose ([rendering-model.md](rendering-model.md)).

### Coordinates & viewport

- Pick one coordinate model per piece of geometry (canvas-px overlay **or**
  base-image-anchored) and stay in that space end to end
  ([coordinate-systems.md](coordinate-systems.md)).
- Treat a viewport-formula output as final — do not recombine it with
  `content_rect_px`, widget size, or zoom “by hand.”
- Convert to device pixels / DPR only inside `record()` when building
  `QRhiScissor` / `QRhiViewport`.
- Route scissors through `resolve_rhi_scissor` (includes offscreen Y-flip)
  ([qrhi-gotchas.md#offscreen-scissor-y-flip](qrhi-gotchas.md#offscreen-scissor-y-flip)).

### Zoom / spit / overlays

- Dual-mode spit: content-anchored at `zoom <= 1`, camera-anchored (clamped)
  only when `zoom > 1`
  ([investigations/divider-zoom-pan-detach.md](investigations/divider-zoom-pan-detach.md)).
- Camera-moved overlays: map through the view transform; do not rely on
  fit-zoom content scissor alone (live magnifier often skips that path).
- Semantic geometry vs paint extents stay separate
  ([zoom-pan.md](zoom-pan.md)).

### QRhiWidget / compositor

- Never enable QWidget autofill on a `QRhiWidget` (no-op like Image Compare)
  ([qrhi-gotchas.md#qrhiwidget-autofill](qrhi-gotchas.md#qrhiwidget-autofill)).
- Live clear color must stay **opaque** (α=255) under the translucent CSD
  shell — otherwise Windows/D3D shows a desktop hole on first present
  ([qrhi-gotchas.md#windows-d3d-empty-first-qrhi-frame--see-through-shell](qrhi-gotchas.md#windows-d3d-empty-first-qrhi-frame--see-through-shell)).
- If the zoom **percent chip** did not move but the picture jumped, treat it
  as display/compositor catch-up until proven otherwise
  ([qrhi-gotchas.md#display-lags-store](qrhi-gotchas.md#display-lags-store)).
- After interactive zoom/pan on MC, settle the compositor on the gesture
  (`rhi_present_sync`), not on the next flyout. IC uses the same flush for
  the first D3D presents.

### Chrome visibility

- Opaque defaults for user-visible chrome (dividers, labels) — weak palette
  Mid / zero alpha looks like “geometry missing”
  ([qrhi-gotchas.md#invisible-chrome-vs-missing-geometry](qrhi-gotchas.md#invisible-chrome-vs-missing-geometry)).

---

## Anti-patterns (do not do this)

### Architecture

- Adding feature logic to `canvas_infra` or new central `if feature == …`
- Duplicating state in feature storage **and** flat `ViewState`
- Putting feature geometry helpers into `canvas_presentation`
- Feature shaders under `shader_sources/` or programs stored on the widget
- PIL/QPainter/CPU fallback render paths for QRhi features
- Per-frame resource creation in `prepare()`/`record()`
- Files past ~400 lines without `File-Size-Exempt:` (see contract tests)

### Coordinates & scissors

- Building `QRhiScissor`/`QRhiViewport` by hand without the
  `y_up OR WA_DontShowOnScreen` rule
  → [qrhi-gotchas.md#offscreen-scissor-y-flip](qrhi-gotchas.md#offscreen-scissor-y-flip)
- Clipping camera-moved overlays with fit-zoom `content_rect_px` scissor
  (or assuming “magnifier is fine” proves that path)
  → [investigations/divider-zoom-pan-detach.md](investigations/divider-zoom-pan-detach.md)
- Screen `vTexCoord` spit for geometry that belongs in letterboxed image UV
- Mixing canvas-px and base-image-anchored models for the same geometry
- Reasoning about DPR before `record()`

### Zoom / store

- Rewriting semantic spit on pan/zoom when `zoom <= 1`, or unclamped camera
  rewrite in the store
  → [investigations/divider-zoom-pan-detach.md](investigations/divider-zoom-pan-detach.md)
- Clamping a display mapping to `[0, 1]` when the point can leave the widget
  at zoom-out
- “Fixing zoom” in Redux/letterbox when the percent chip did not change
  → [investigations/mc-transient-zoom-nudge.md](investigations/mc-transient-zoom-nudge.md)

### QRhi / Wayland mitigations already falsified

Do **not** reintroduce these for the MC “first flyout after zoom” jump:

- `menu_parent=MainWindow` + `popup` (one-frame clear wipe)
- `setUpdatesEnabled(False)` around the menu (halo; jump can remain with
  **no** app present)
- Color-buffer freeze / force `in_window` alone as the fix
- Assuming keyboard-focus parking alone restores `ApplicationActive`

Details: [qrhi-gotchas.md#display-lags-store](qrhi-gotchas.md#display-lags-store),
[investigations/mc-transient-zoom-nudge.md](investigations/mc-transient-zoom-nudge.md).

### Blending / visibility

- Default `TargetBlend` alpha that mirrors color factors — set
  `srcAlpha = One`, `dstAlpha = OneMinusSrcAlpha` explicitly
- Feature-local mode services for export visibility when `SceneVisibility`
  already expresses it
- Executor flags like `hide_in_single_preview`
