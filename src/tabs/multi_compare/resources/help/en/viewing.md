## Multi Compare Viewing

Viewing controls how the grid is displayed and never touches the source files.

### Focus mode {#focus-mode}

Click a **slot** (a grid cell holding one image) to focus it: the rest of the grid dims and that slot fills the view. A press that turns into a drag moves the slot instead, and clicking the dimmed area or pressing `Esc` leaves focus. Zoom and pan keep working while a slot is focused.

### Zoom and pan {#zoom-and-pan}

- **Shared view** — zoom and pan apply to the whole grid, not to each slot separately.
- **Wheel** — zooms from 1.0x to 50x in 1.1x steps; the point under the cursor stays in place.
- **Pan limits** — panning stops at the edge of the image; at fit size or smaller the view snaps back.
- **Middle-drag** — drag with the middle mouse button to pan.
- **`0`** — resets zoom and pan.

### Keyboard {#keyboard}

The shortcuts for this tab are listed in [Hotkeys](help://platform.hotkeys).

### Grid and labels {#grid-and-labels}

The divider settings live in [Multi Compare Layouts](help://workspace.multi_compare.layouts#dividers). **Label Settings** opens a panel that styles the slot label text.

### Slot crop {#slot-crop}

Crop trims the black borders off a slot's image. Each slot is set to on, off, or to follow the global auto-crop setting: a slot that follows it changes with that setting, while a slot set to on or off keeps its choice. An empty slot has nothing to crop. The crop shows in the grid and in saved images.
