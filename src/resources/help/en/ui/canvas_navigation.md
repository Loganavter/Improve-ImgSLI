## Canvas Navigation

Move inside the compare canvas: zoom toward the cursor, pan with the middle button, and hold `Space` for a temporary full-side preview.

### Zoom and pan {#zoom}

- **Zoom** — hold `Ctrl` and scroll the wheel over the canvas; zoom is cursor-centered.
- **Pan** — hold the middle mouse button and drag, including at `100%` zoom.
- **Mode** — there is no separate navigation tool; these gestures work on the live canvas.

:::figure{side=right width=280}
![Canvas zoom and pan](ui/placeholder.png)
{{tr:workspace.session_types.image_compare}} → canvas (placeholder).
:::

### Quick side preview {#quick-side-preview}

- **Side 1** — hold `Space`, then `LMB`.
- **Side 2** — hold `Space`, then `RMB`.
- **Release** — return to the normal split.
- **With combined magnifier** — hold `Space+Shift` to force a side inside the lens.

### While zoomed {#zoom-side-effects}

- **Filename labels** — visible only at `100%` zoom; they return automatically when you fit again.
- **Split line** — keeps a stable screen position as zoom changes.
- **Quality** — preview cache and interpolation live under [Settings → Performance](help://settings#performance).
