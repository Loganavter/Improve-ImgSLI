## Multi Compare Export

The grid saves as a single image, and the session keeps the grid so it returns when reopened.

### Save and export {#save-and-export}

- **Quick Save** (`Ctrl+S`) — writes the image with the settings used last, without a dialog.
- **Save Grid** — opens the save dialog through **Find Action**; see [Export](help://workspace.export).
- **Result** — the saved image shows the grid as it appears on screen.
- **Crop** — each slot's crop is applied before the slots are combined.
- **Empty slots** — slots without an image are left out of the saved image.
- **Large exports** — if the longer side is over 16384 px, a warning asks whether to continue, because larger sizes have not been tested and the export may fail or run out of memory. **Cancel** stops the export; **Don't show again** turns the warning off for later exports.

### Sessions {#sessions}

A session stores the image paths and labels of its slots, the layout, the focused slot, zoom and pan, and the label and divider styling. The image files themselves are not copied — the session reopens them from their paths on disk.

- **Reopening** — a reopened session shows its slots right away and loads its images from their paths; a session that is not active loads its images when it becomes active.
- **New sessions** — a new session starts with the divider and label styling used last.
