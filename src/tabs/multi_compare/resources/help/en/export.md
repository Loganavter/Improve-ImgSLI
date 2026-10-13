## Multi Compare Export

The grid saves as one image through quick save or the save dialog. A session keeps its grid, so reopening the session brings the layout back.

### Save and export {#save-and-export}

- **Quick save** (`Ctrl+S`) — {{tr:multi_compare.action.quick_save}} writes the image with the settings you used last, without a dialog.
- **Save dialog** — {{tr:multi_compare.action.save}} via {{tr:menu.find_action}}; see [Export](help://workspace.export).
- **Result** — the saved image shows the grid as it appears on screen.
- **Crop** — each slot's crop is applied before the slots are combined.
- **Empty slots** — slots without an image are left out of the saved image.
- **Large exports** — if the longer side is over 16384 px, a warning asks whether to continue. Sizes beyond that have not been tested, so the export may fail or run out of memory. Cancel stops the export. Checking "Don't show again" turns the warning off for later exports.

### Sessions {#sessions}

A session stores the slot image paths and labels, the layout, the focused slot, zoom and pan, and the label and divider styling.

- **Reopening** — a session shows its slots when it opens. Its images load again from their file paths; a session that is not active loads its images when you switch to it.
- **New sessions** — a new session starts with the divider and label styling you used last.
