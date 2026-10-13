## Magnifier

The magnifier samples a region of the compared pair and shows an enlarged view on the canvas, so you can study local detail beyond the split line.

### Enabling {#enabling}

- **Toggle** — the **Toggle Magnifier** control on the toolbar, or `M`, shows or hides the lens.
- **Place** — click or drag on the image to set the capture area (the red capture ring).
- **Ring** — the capture ring size and color follow the lens styling.

:::figure{side=block width=280}
![Magnifier lens](../assets/magnifier.jpg)
The magnifier lens on the canvas and the red capture ring that marks the sampled area.
:::

### Size and movement {#size-and-movement}

- **Lens size** — **Magnifier Size (%)** sets how large the lens is drawn on the canvas.
- **Capture size** — **Capture Size (%)** sets how much source area the lens samples; a larger value shows more of the image at less magnification.
- **Move** — with the lens active, `WASD` moves it over the image.
- **Spacing** — `QE` changes how far apart the two halves of the lens are while they are separated; each half shows one of the compared images.
- **Speed** — **Move Speed** sets how fast the lens moves while you hold a `WASD` key. The control is on the magnifier panel while that panel is shown.

### Freeze {#freeze}

**Freeze Magnifier** (`F`) pins the lens to its current position on the canvas, so you can pan the capture area without the lens following. Keyboard movement still nudges the frozen lens.

### Divider, guides, and colors {#guides-and-colors}

- **Orientation** — **Magnifier Orientation** switches the lens halves between side-by-side and stacked.
- **Internal divider** — **Magnifier Divider** sets orientation, thickness, and color of the split inside the lens (scroll / right-click).
- **Visibility** — **Magnifier Divider Visibility** and **Magnifier Guides** show or hide the internal split and the guide lines; their widths are set separately.
- **Colors** — **Magnifier Colors** sets the outline color of each lens instance.

### Multiple instances {#instances}

- **Add / remove** — **Magnifier Instances** lets you watch several regions at once.
- **Auto-color** — with the option enabled in Settings, new instances can get distinct colors.

### Combined mode {#combined-mode}

- **Merge** — when both halves stay visible and their spacing closes to the combine threshold, they merge into one lens.
- **Internal split** — drag with the right mouse button inside the lens.
- **Side preview** — `Shift` + `Space` temporarily forces one side inside the combined lens.

:::figure{side=block width=280}
![Combined magnifier](../assets/magnifier_combined.jpg)
Toggle Magnifier combined mode.
:::

For a full-canvas compare without the lens, see [Comparison](help://workspace.image_compare.comparison).

### Settings that affect the magnifier {#related-settings}

Magnifier-related options live under [Settings](help://platform.settings#image_compare):

- **Magnifier movement** — optimizes how the lens follows the pointer, together with its interpolation method.
- **Red highlight for overlapping magnifiers** — marks lenses that intersect in red.
- **Auto-color new magnifiers** — gives each new instance its own outline color.
