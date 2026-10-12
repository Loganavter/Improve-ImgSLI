## Multi Compare Layouts

Slots sit in a split grid with per-cell drops, gap splits, and draggable dividers.

### Cells and drop zones {#layouts}

- **Grid** — slots take file drops or {{tr:multi_compare.action.add_images}} (`Ctrl+O`).
- **Empty slots** — stay open for new drops.
- **Outside drops** — file-manager drops, clipboard paste, or **Move** from another tab auto-place with a loading toast.
- **Auto-place** — new images split the largest cell along its longer axis.
- **Gap drop** — a drop in a divider gap splits a new cell between the neighbours.
- **Layout change** — keeps loaded images.

### Gap split zones {#gap-split-zones}

- **Vertical divider gap** — top quarter inserts above the row, bottom quarter below, middle half between neighbours.
- **Horizontal divider gap** — left quarter inserts left of the column, right quarter right, middle half between neighbours.

### Dividers {#dividers}

- **Drag** — grid dividers change relative sizes; splits store weights.
- **Reset** — double-click resets the split to equal weights.
- **Visibility** (`D`) — {{tr:multi_compare.action.divider_visible}}.
- **Color / width** — {{tr:multi_compare.action.divider_color}} and {{tr:multi_compare.action.divider_width}}.

### Slot actions {#context-menu}

Per-image actions:

- **Rename** — edits the slot label.
- **Duplicate** — copies the slot; needs a loaded image and a free slot.
- **Properties** — [Image Properties](help://image_properties) with file metadata and grid position.
- **Move** — drag ghost loads the image on another tab, auto-placed.
- **Crop** — per-slot crop override; see [Viewing](help://mc_viewing).
- **Remove** — drops the slot from the grid.
- **Cap** — the grid holds at most 12 images.
