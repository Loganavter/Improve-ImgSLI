## Canvas Navigation

Movement inside the compare canvas: cursor-centered zoom, middle-button pan, `Space` full-side preview.

### Zoom and pan {#zoom}

- **Zoom** — `Ctrl` + wheel over the canvas; cursor-centered.
- **Pan** — middle mouse button + drag, including at `100%` zoom.
- **Mode** — no separate navigation tool; these gestures work on the live canvas.

:::figure{side=block width=280}
![Canvas zoom and pan]({{img:ui.canvas_navigation.zoom}})
{{tr:workspace.session_types.image_compare}} → canvas.
:::

### Quick side preview {#quick-side-preview}

- **Side 1** — `Space` + `LMB`.
- **Side 2** — `Space` + `RMB`.
- **Release** — return to the normal split.
- **With combined magnifier** — `Space+Shift` forces a side inside the lens.

### While zoomed {#zoom-side-effects}

- **Filename labels** — visible only at `100%` zoom; reappear on fit.
- **Split line** — keeps a stable screen position as zoom changes.
- **Quality** — preview cache and interpolation live under [Settings → Performance](help://settings#performance).
