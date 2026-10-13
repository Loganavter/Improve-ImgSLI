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

- **Vertical divider gap** — dropping on the top quarter of the gap places the image above the row, the bottom quarter below it, and the middle half between the two neighbouring slots.
- **Horizontal divider gap** — dropping on the left quarter of the gap places the image left of the column, the right quarter right of it, and the middle half between the two neighbouring slots.

### Dividers {#dividers}

- **Drag** — moves a divider and changes the relative size of the cells on either side.
- **Reset** — double-click a divider to make the cells on either side equal.
- **Visibility** (`D`) — {{tr:multi_compare.action.divider_visible}}.
- **Color / width** — {{tr:multi_compare.action.divider_color}} and {{tr:multi_compare.action.divider_width}}.

### Slot actions {#context-menu}

Per-image actions:

- **Rename** — edits the slot label.
- **Duplicate** — copies the slot; needs a loaded image and a free slot.
- **Properties** — [Image Properties](help://platform.image_properties) with file metadata and grid position.
- **Move** — drags the image onto another tab, where it loads and is placed automatically.
- **Crop** — turns crop on or off for this slot; see [Viewing](help://workspace.multi_compare.viewing#slot-crop).
- **Remove** — drops the slot from the grid.
- **Cap** — the grid holds at most 12 images.
