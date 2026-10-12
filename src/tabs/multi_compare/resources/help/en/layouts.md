## Multi Compare Layouts

Arrange slots in a split grid: drop images into cells, split gaps for new cells, and drag dividers to resize.

### Cells and drop zones {#layouts}

- **Grid** — arrange slots; drop files onto a cell or use {{tr:multi_compare.action.add_images}} (`Ctrl+O`).
- **Empty slots** — stay open for new drops.
- **Outside drops** — files dropped from a file manager, clipboard paste, or **Move** from another tab load immediately into auto-placed slots with a loading toast; there is no click-to-place step and no armed highlight to cancel.
- **Auto-place** — a new image splits the largest cell along its longer axis, so the grid stays balanced without manual targeting.
- **Gap drop** — drop onto a gap between cells to split and create a new cell recursively.
- **Layout change** — keeps loaded images where possible.

### Gap split zones {#gap-split-zones}

- **Vertical divider gap** (side-by-side cells) — drop in the top quarter to insert above the whole row, the bottom quarter to insert below it, or the middle half to insert between the two neighbouring cells.
- **Horizontal divider gap** (stacked cells) — drop in the left quarter to insert left of the whole column, the right quarter to insert right of it, or the middle half to insert between the two neighbouring cells.

### Dividers {#dividers}

- **Drag** — drag a grid divider to change relative sizes; each split stores weights and a cell's share is its weight over the total.
- **Reset** — double-click a divider to reset its split to equal weights.
- **Visibility** (`D`) — {{tr:multi_compare.action.divider_visible}}.
- **Color / width** — {{tr:multi_compare.action.divider_color}} and {{tr:multi_compare.action.divider_width}}.

### Slot actions {#context-menu}

Right-click a slot for per-image actions:

- **Rename** — edit the slot label.
- **Duplicate** — copy the slot; needs a loaded image and a free slot.
- **Properties** — [Image Properties](help://image_properties) with file metadata and the slot position in the grid.
- **Move** — drag ghost onto another workspace tab to load the image there immediately, auto-placed.
- **Crop** — per-slot crop override checkbox; see [Viewing](help://mc_viewing).
- **Remove** — drop the slot from the grid.
- **Cap** — the grid holds at most 12 images.
