## Multi Compare Export

The grid saves as one image via quick save or the save dialog; sessions keep the layout.

### Save and export {#save-and-export}

- **Quick save** (`Ctrl+S`) — {{tr:multi_compare.action.quick_save}} saves with last settings, no dialog.
- **Save dialog** — {{tr:multi_compare.action.save}} via {{tr:menu.find_action}}; see [Export](help://export).
- **Parity** — export matches the live grid, not a single {{tr:workspace.session_types.image_compare}} split.
- **Crop** — per-slot crop clips before composition.
- **Empty slots** — unloaded cells skip, never blank.
- **Large exports** — far above tested size asks first.

### Sessions {#sessions}

- **Payload (v1)** — slot paths, labels, layout tree, focus, zoom, pan, styling.
- **Lazy reopen** — paths first, decoding on demand; dormant fill on activation.
- **Chrome seeding** — new sessions reuse last divider and label styling.
