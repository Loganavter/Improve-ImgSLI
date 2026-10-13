## Comparison

Compare two images across the whole canvas: drag a movable split line, show filename labels, inspect single color channels, and highlight where the images differ — without opening the magnifier.

### Split line {#split-line}

With the magnifier off, drag the divider across the pair.

- **Orientation** — the **Split Orientation** control switches the split between horizontal and vertical.
- **Width** — scroll over **Divider Width** to change how thick the split line is.
- **Color** — **Divider Color** sets the line color.
- **Visibility** (`D`) — the **Divider Visibility** toggle shows or hides the line.
- **Combined** — the **Divider** control packs orientation, width, and color into one control (scroll / right-click / middle-click); hover it to see the gesture tooltip.

:::figure{side=block width=280}
![Split line](../assets/split_line.png)
The split line on the canvas: drag it to reveal the same position on both sides.
:::

### Scroll through images {#scroll-images}

- **Canvas wheel** — scrolling steps the list on the side under the cursor (left of a vertical split, or above a horizontal split, is side 1; the other half is side 2).
- **`Shift` + wheel** — scrolling steps both lists together.
- **Single-image preview** — when only one image is shown, the wheel always steps the visible side.
- **Dropdown wheel** — scrolling over the dropdown steps that side without opening its panel.
- **Swap** (`X`) — a short click exchanges the current pair; a long press swaps both lists.

### Labels {#labels-and-metrics}

- **Show names** (`N`) — when the **Filename Overlay** toggle is on, filename labels appear on the canvas and can be written into saved images.
- **Zoom** — labels are hidden while the view is zoomed and come back at `100%` zoom.
- **Text settings** — **Label Text Settings** opens a panel for font size, weight, opacity, colors, background, and placement.

### Metrics {#metrics}

- **PSNR / SSIM** — the readout is off by default. Turn on the automatic PSNR and SSIM calculation under **Image Compare** in [Settings](help://platform.settings#image_compare).

### Moving an image between tabs {#moving-between-tabs}

The **Move** action sends an image to another workspace tab without copying it into the project first.

1. In the image context menu on the canvas or in the list, choose **Move**.
2. A translucent copy of the image appears next to the cursor.
3. Click the workspace tab or the canvas where you want to place the image — the same placement as Duplicate or paste.
4. Press `Esc` or right-click to cancel the move.

### Context menu actions {#context-menu-actions}

- **Properties** — [Image Properties](help://platform.image_properties) from a list-row context menu shows the file metadata and the in-app side and rating.

### Channel modes {#channel-modes}

**Channel Mode** (`C`) cycles RGB, R, G, B, and luminance so you can inspect a single channel without leaving the canvas.

### Difference modes {#difference-modes}

**Difference Mode** (`H` cycles) emphasizes where the pair differs:

:::figure{side=block width=280}
![Difference mode](../assets/difference_modes.png)
The same pair in each difference mode: **Highlight**, grayscale, edges, and SSIM show the differences in different ways.
:::

- **Highlight** — colors the regions where the two images differ.
- **Grayscale** — desaturates the intensity differences.
- **Edges** — shows the difference along edges.
- **SSIM** — draws a structural similarity map of the pair.

The live canvas, exported stills, and video recording keep the same look. Difference modes combine with channel views. For local inspection, use the [Magnifier](help://workspace.image_compare.magnifier).
