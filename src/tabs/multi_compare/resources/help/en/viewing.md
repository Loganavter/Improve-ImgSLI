## Multi Compare Viewing

Focus one image, zoom and pan the whole grid, style labels, and control per-slot crop.

### Focus mode {#focus-mode}

- **Enter** — single-click a slot for full-canvas focus (a press that turns into a drag starts a move instead).
- **Exit** — click the dimmed area around the image or press `Esc` to return to the grid.
- **Navigate** — zoom and pan like {{tr:workspace.session_types.image_compare}}; see [Canvas Navigation](help://view_navigation).

### Zoom and pan {#zoom-and-pan}

- **Shared view** — zoom and pan apply to the whole grid at once, not per slot.
- **Wheel** — zoom under the cursor from 1.0x to 50x in 1.1x steps; the content point under the cursor stays put.
- **Pan clamp** — the viewport never shows void past the image; at fit and below, pan snaps back to the origin.
- **Middle-drag** — drag with the middle mouse button to pan.
- **`0`** — reset zoom and pan.

### Keyboard {#keyboard}

- `Ctrl+O` — {{tr:multi_compare.action.add_images}}.
- `D` — {{tr:multi_compare.action.divider_visible}}.
- `Ctrl+S` — {{tr:multi_compare.action.quick_save}}.
- `Arrow keys` — pan the view.
- `+` / `-` — zoom in / out.
- `Esc` — leave focus mode.
- `0` — reset zoom and pan.

### Grid and labels {#grid-and-labels}

- **Visibility** (`D`) — {{tr:multi_compare.action.divider_visible}}.
- **Color / width** — {{tr:multi_compare.action.divider_color}} and {{tr:multi_compare.action.divider_width}}.
- **Label text** — {{tr:multi_compare.action.text_settings}} opens styling (no placement radios from {{tr:workspace.session_types.image_compare}}).

### Slot crop {#slot-crop}

- **Checkbox** — the slot context menu's Crop entry is a checkbox showing the effective state; flipping it writes an explicit on/off override for that slot.
- **Auto** — a slot left on Auto follows the global black-border auto-crop setting; an empty slot has nothing to crop and stays Auto.
- **Render and export** — crop applies when the slot is sampled, so zoom fit and export both see the cropped size; a slot whose crop window misses the frame entirely is skipped like an empty one.
