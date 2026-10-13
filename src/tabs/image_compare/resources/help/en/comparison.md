## Comparison

Two images on the full canvas: a movable split, optional filename labels, channel views, and difference modes — without opening the magnifier.

### Split line {#split-line}

With the magnifier off, drag the divider across the pair.

- **Orientation** — {{tr:image_compare.action.divider_orientation}} flips horizontal / vertical.
- **Width** — scroll over {{tr:image_compare.action.divider_width}}.
- **Color** — {{tr:image_compare.action.divider_color}}.
- **Visibility** (`D`) — {{tr:image_compare.action.divider_visible}} shows or hides the line.
- **Combined** — {{tr:image_compare.action.divider_combined}} packs orientation, width, and color (scroll / right-click / middle-click); see the control tooltip.

:::figure{side=block width=280}
![Split line]({{img:workspace.image_compare.comparison.split_line}})
{{tr:image_compare.action.breadcrumb.toolbar}} → {{tr:image_compare.action.breadcrumb.divider}}.
:::

### Scroll through images {#scroll-images}

- **Canvas wheel** — steps the list on the side under the cursor (left of a vertical split / above a horizontal split = side 1; the other half = side 2).
- **`Shift` + wheel** — steps both lists together.
- **Single-image preview** — wheel always steps the visible side.
- **Dropdown wheel** — steps that side without opening the panel.
- **Swap** (`X`) — short click exchanges the current pair; long-press swaps both lists.

### Labels {#labels-and-metrics}

- **Show names** (`N`) — {{tr:image_compare.action.file_names}}; can burn into exports when enabled.
- **Zoom** — labels hide while zoom is not `100%` and return at fit zoom.
- **Text settings** — {{tr:image_compare.action.text_settings}} opens a panel for size, weight, opacity, colors, background, and placement.

### Metrics {#metrics}

- **{{tr:image_compare.ui.psnr}} / {{tr:image_compare.ui.ssim}}** — off by default; turn on the automatic readout in [Settings](help://platform.settings#image_compare) under {{tr:workspace.session_types.image_compare}}.

### Context menu actions {#context-menu-actions}

- **Properties** — [Image Properties](help://platform.image_properties) from a list-row context menu (file metadata and in-app side / rating).
- **Move** — from the canvas or list context menu, a preview of the image follows the pointer. Click another workspace tab or the canvas to place it, as with Duplicate or paste. `Esc` or right-click cancels.

### Channel modes {#channel-modes}

{{tr:image_compare.action.channel_mode}} (`C`) cycles RGB, R, G, B, and luminance for single-channel inspection without leaving the canvas.

### Difference modes {#difference-modes}

{{tr:image_compare.action.diff_mode}} (`H` cycles) emphasizes where the pair differs:

:::figure{side=block width=280}
![Difference mode]({{img:workspace.image_compare.comparison.difference_modes}})
{{tr:image_compare.action.diff_mode}}.
:::

- **{{tr:image_compare.action.diff_highlight}}** — change regions on the live pair
- **{{tr:image_compare.action.diff_grayscale}}** — desaturates intensity differences
- **{{tr:image_compare.action.diff_edges}}** — edge-oriented difference
- **{{tr:image_compare.action.diff_ssim}}** — structural similarity map when metrics support it

Live canvas, export stills, and video recording keep the same look. Difference modes combine with channel views. For local inspection, use the [Magnifier](help://workspace.image_compare.magnifier).
