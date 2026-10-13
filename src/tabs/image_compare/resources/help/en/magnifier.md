## Magnifier

The magnifier enlarges a chosen region of the two compared images, so you can study detail that is too small on the canvas.

### Enabling {#enabling}

- **Toggle Magnifier** (`M`) — shows or hides the lens on the canvas. The other controls on this page apply only while the lens is shown.
- **Capture Ring** — the red ring around the region the lens enlarges. Click or drag on an image to move that region.

:::figure{side=block width=280}
![Magnifier lens](../assets/magnifier.jpg)
The two magnifier halves on the canvas, and the red **Capture Ring** on the image.
:::

### Size and movement {#size-and-movement}

- **Magnifier Size (%)** — how large the lens is drawn on the canvas.
- **Capture Size (%)** — how much of the image the lens samples; a larger value shows more of the image at a lower magnification.
- With the lens shown, `WASD` moves it across the image, and `QE` changes how far apart its two **halves** are while they are separated. The halves are the two parts of the lens; each shows one of the compared images.
- **Move Speed** — how fast the lens moves while a `WASD` key is held; the slider sits on the magnifier panel, shown with the lens.

### Freeze {#freeze}

**Freeze Magnifier** (`F`) pins the lens to its current spot on the canvas, so the **Capture Ring** can move without the lens following it. Press `F` again to release the lens.

### Divider, guides, and colors {#guides-and-colors}

- **Magnifier Orientation** — switches the two halves between side-by-side and stacked.
- **Magnifier Divider** — sets the orientation, thickness, and color of the split inside the lens (scroll / right-click).
- **Magnifier Divider Visibility** and **Magnifier Guides** — show or hide that split and the guide lines; the guide thickness is set separately.
- **Magnifier Colors** — sets the outline color of the lens.

### Multiple instances {#instances}

- **Magnifier Instances** — add and remove lenses to watch several regions at once.
- **Auto-color new magnifiers** — when this option is on in [Settings](help://platform.settings#image_compare), each new lens gets its own outline color.

### Combined mode {#combined-mode}

When both halves stay visible and their spacing closes to the merge threshold, they merge into a single lens.

- **Internal split** — drag with the right mouse button inside the merged lens to move the split between the halves.
- **Side preview** — `Shift` + `Space` temporarily forces one side to fill the merged lens.

:::figure{side=block width=280}
![Combined magnifier](../assets/magnifier_combined.jpg)
The combined lens: the two halves merged into one.
:::

For a full-canvas compare without the lens, see [Comparison](help://workspace.image_compare.comparison).

### Settings that affect the magnifier {#related-settings}

Magnifier-related options live under [Settings](help://platform.settings#image_compare):

- **Magnifier movement** — keeps the lens following the pointer smooth while you drag it.
- **Laser smoothing** — smooths the magnifier guides.
- **Red highlight for overlapping magnifiers** — marks the part of a lens that another lens overlaps.
- **Auto-color new magnifiers** — gives each new lens its own outline color.
