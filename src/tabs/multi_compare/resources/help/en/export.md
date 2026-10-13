## Multi Compare Export

The grid saves as one image through quick save or the save dialog. A session keeps its grid, so reopening the session brings the layout back.

### Save and export {#save-and-export}

- **Quick save** (`Ctrl+S`) — writes the image with the settings you used last, without a dialog.
- **Save Grid** — opens the save dialog through **Find Action**; see [Export](help://workspace.export).
- **Result** — the saved image shows the grid as it appears on screen.
- **Crop** — each slot's crop is applied before the slots are combined.
- **Empty slots** — slots without an image are left out of the saved image.
- **Large exports** — if the longer side is over 16384 px, a warning asks whether to continue, because larger sizes have not been tested and the export may fail or run out of memory. **Cancel** stops the export; **Don't show again** turns the warning off for later exports.

### Sessions {#sessions}

A session stores the slot image paths and labels, the layout, the focused slot, zoom and pan, and the label and divider styling. The image files themselves are not copied; the session reopens them from their paths on disk.

- **Reopening** — a session shows its slots when it opens. Its images load again from their file paths; a session that is not active loads its images when you switch to it.
- **New sessions** — a new session starts with the divider and label styling you used last.
