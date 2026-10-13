## Multi Compare Layouts

The grid gives each image its own **slot**, and the **dividers** between slots set how much room each one takes.

### Cells and drop zones {#layouts}

- **Add Images** (`Ctrl+O`) — loads one or more images into the grid.
- **File drops** — a file dropped on the grid opens a slot beside the cell under the cursor and splits it; the first drop on an empty grid becomes the first slot. A drop targets the nearest of the cell's four edges.
- **Outside drops** — files dropped from the file manager, pasted from the clipboard, or moved with **Move** from another tab are placed automatically while a progress message shows.
- **Auto-place** — a newly added image splits the largest cell along its longer side.
- **Gap drop** — a drop in a divider gap splits a new cell between the two neighbouring slots.
- **Layout change** — changing the layout keeps the loaded images and only rearranges them.

### Gap split zones {#gap-split-zones}

When an image is dropped into the gap between two slots, the spot inside the gap decides where the new cell goes.

- **Vertical divider gap** — dropping in the top quarter of the gap places the image above the row, the bottom quarter places it below, and the middle half places it between the two neighbouring slots.
- **Horizontal divider gap** — dropping in the left quarter places the image left of the column, the right quarter places it right, and the middle half places it between the two neighbouring slots.

### Dividers {#dividers}

- **Drag** — drag a divider to change the relative size of the cells on either side.
- **Reset** — double-click a divider to make the cells on either side equal.
- **Grid Visibility** (`D`) — shows or hides the divider lines.
- **Grid Color** and **Grid Lines** — set the colour and width of the divider lines.

### Slot actions {#context-menu}

Right-click a slot for per-image actions:

- **Rename** — edits the name shown on the slot label.
- **Duplicate** — copies the slot; it needs a loaded image.
- **Properties** — opens [Image Properties](help://platform.image_properties) with the file metadata and the slot's grid position.
- **Move** — hands the image to another tab, where it loads and is placed automatically.
- **Crop** — turns crop on or off for this slot; see [Multi Compare Viewing](help://workspace.multi_compare.viewing#slot-crop).
- **Remove** — removes the slot and its image from the grid.
