## Multi Compare Layouts

Slots sit in a split grid where you can drop files, split cells at a gap, and drag the dividers to resize them.

### Cells and drop zones {#layouts}

- **File drops** — drop a file onto the grid; the new slot opens beside the cell under the cursor and splits it, and the first drop on an empty grid becomes the first slot.
- **Add Images** (`Ctrl+O`) — loads one or more images into the grid.
- **Drop zones** — a file drop targets the cell under the cursor and the nearest of its four edges.
- **Outside drops** — files dropped from the file manager, pasted from the clipboard, or moved with **Move** from another tab are placed automatically while a progress message shows.
- **Auto-place** — a new image splits the largest cell along its longer side, and the grid holds at most 12 images.
- **Gap drop** — a drop in a divider gap splits a new cell between the two neighbouring slots.
- **Layout change** — changing the layout keeps the loaded images and only rearranges them.

### Gap split zones {#gap-split-zones}

When you drop an image into a gap between two slots, the spot inside the gap decides where the new cell goes.

- **Vertical divider gap** — dropping in the top quarter of the gap places the image above the row, the bottom quarter places it below, and the middle half places it between the two neighbouring slots.
- **Horizontal divider gap** — dropping in the left quarter places the image left of the column, the right quarter places it right, and the middle half places it between the two neighbouring slots.

### Dividers {#dividers}

- **Drag** — drag a divider to change the relative size of the cells on either side.
- **Reset** — double-click a divider to make the cells on either side equal.
- **Grid Visibility** (`D`) — shows or hides the divider lines.
- **Grid Color** and **Grid Lines** — set the color and width of the divider lines.

### Slot actions {#context-menu}

Right-click a slot for per-image actions:

- **Rename** — edits the name shown on the slot label.
- **Duplicate** — copies the slot; it needs a loaded image and a free slot.
- **Properties** — opens [Image Properties](help://platform.image_properties) with the file metadata and the slot's grid position.
- **Move** — drags the image onto another tab, where it loads and is placed automatically.
- **Crop** — turns crop on or off for this slot; see [Multi Compare Viewing](help://workspace.multi_compare.viewing#slot-crop).
- **Remove** — removes the slot and its image from the grid.
- **Slot limit** — you can load at most 12 images into one grid.
