## Canvas Navigation

Movement inside the compare canvas: cursor-centered zoom, middle-button pan, `Space` full-side preview.

### Zoom and pan {#zoom}

- **Zoom** — `Ctrl` + wheel over the canvas.
- **Pan** — middle mouse button + drag.
- **Navigation tool** — none; gestures work directly on the live canvas.

:::figure{side=block width=280}
![Canvas zoom and pan]({{img:ui.canvas_navigation.zoom}})
{{tr:workspace.session_types.image_compare}} → canvas.
:::

### Quick side preview {#quick-side-preview}

Compare-canvas gesture (see [Comparison](help://comparison)):

- **Left side** — `Space` + `LMB`.
- **Right side** — `Space` + `RMB`.
- **Release** — back to the normal split.
- **With combined magnifier** — `Space+Shift` forces a side inside the lens (see [Magnifier](help://magnifier)).

### While zoomed {#zoom-side-effects}

- **Filename labels** — visible only at `100%` zoom; reappear on fit.
- **Split line** — fractional position (0–1); the fraction holds while zoom changes.
- **Render quality** — interpolation lives in the canvas flyout; backend switch under [Settings → Performance](help://settings#performance).
