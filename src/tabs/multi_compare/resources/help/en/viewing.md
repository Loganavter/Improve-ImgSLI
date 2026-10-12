## Multi Compare Viewing

Viewing covers focus mode, shared zoom and pan, labels, and per-slot crop.

### Focus mode {#focus-mode}

- **Enter** — single-click focuses a slot; a press turning to a drag moves instead.
- **Exit** — dimmed-area click or `Esc` exits.
- **Navigate** — zoom and pan like {{tr:workspace.session_types.image_compare}}; see [Canvas Navigation](help://view_navigation).

### Zoom and pan {#zoom-and-pan}

- **Shared view** — zoom and pan apply grid-wide, not per slot.
- **Wheel** — zoom under the cursor, 1.0x–50x in 1.1x steps; the point stays put.
- **Pan clamp** — no void past the image; at fit and below, pan snaps back.
- **Middle-drag** — middle-button drag pans.
- **`0`** — resets zoom and pan.

### Keyboard {#keyboard}

- `Ctrl+O` — {{tr:multi_compare.action.add_images}}.
- `D` — {{tr:multi_compare.action.divider_visible}}.
- `Ctrl+S` — {{tr:multi_compare.action.quick_save}}.
- `Arrow keys` — pans.
- `+` / `-` — zooms.
- `Esc` — leaves focus.
- `0` — resets view.

### Grid and labels {#grid-and-labels}

- **Visibility** (`D`) — {{tr:multi_compare.action.divider_visible}}.
- **Color / width** — {{tr:multi_compare.action.divider_color}} and {{tr:multi_compare.action.divider_width}}.
- **Label text** — {{tr:multi_compare.action.text_settings}} styling without {{tr:workspace.session_types.image_compare}} radios.

### Slot crop {#slot-crop}

- **Checkbox** — Crop entry shows state; flipping writes an on/off override.
- **Auto** — Auto follows global auto-crop; empty slots stay Auto.
- **Render and export** — crop applies at sampling; missed frames skip as empty.
