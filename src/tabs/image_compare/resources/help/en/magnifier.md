## Magnifier

The magnifier samples a region of the compared images and shows an enlarged view on the canvas. Use it when the split line alone is not enough for a local detail.

### Enabling {#enabling}

- **Toggle** — {{tr:image_compare.action.magnifier}} on the toolbar, or `M`.
- **Place** — click or drag on the image to set the capture area (red circle).
- **Ring** — capture-ring size and color follow the lens styling.

:::figure{side=block width=280}
![Magnifier lens]({{img:workspace.image_compare.magnifier.enabling}})
{{tr:image_compare.action.breadcrumb.toolbar}} → {{tr:image_compare.action.breadcrumb.magnifier}}.
:::

### Size and movement {#size-and-movement}

- **Lens size** — {{tr:label.magnifier_size}}.
- **Capture size** — {{tr:label.capture_size}} (how much source area is sampled).
- **Move** — `WASD` with the lens active; `QE` adjusts spacing when halves are separated.
- **Speed** — on the magnifier panel when it is shown.

### Freeze {#freeze}

{{tr:image_compare.action.freeze}} (`F`) locks the lens on screen so you can nudge it with the keyboard while the pointer stays free.

### Divider, guides, and colors {#guides-and-colors}

- **Orientation** — {{tr:image_compare.action.magnifier_orientation}}.
- **Internal divider** — {{tr:image_compare.action.magnifier_divider_combined}} (scroll / right-click).
- **Visibility** — {{tr:image_compare.action.magnifier_divider_visible}} and {{tr:image_compare.action.magnifier_guides}}, plus their widths.
- **Colors** — {{tr:image_compare.action.magnifier_colors}} for per-instance outline colors.

### Multiple instances {#instances}

- **Add / remove** — {{tr:image_compare.action.magnifier_instances}} to watch several regions.
- **Auto-color** — new instances can get distinct colors when that option is on in Settings.

### Combined mode {#combined-mode}

- **Merge** — when the halves sit close enough, or a difference mode is active, they become one lens.
- **Internal split** — drag with `RMB` inside the lens.
- **Side preview** — `Space+Shift` can force a side preview while the lens is active.

:::figure{side=block width=280}
![Combined magnifier]({{img:workspace.image_compare.magnifier.combined_mode}})
{{tr:image_compare.action.magnifier}} combined mode.
:::

For a full-canvas compare without the lens, see [Comparison](help://comparison).

### Settings that affect the magnifier {#related-settings}

Under [Settings → Performance](help://settings#performance):

- Optimize magnifier movement and its interpolation
- Intersection highlight between lenses
- Auto-color for new instances

Display-cache limits apply to the main preview only — the magnifier still samples originals.
