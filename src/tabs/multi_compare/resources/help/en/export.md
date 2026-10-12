## Multi Compare Export

Save the grid as one image with quick save or the save dialog; sessions keep the layout for later.

### Save and export {#save-and-export}

- **Quick save** (`Ctrl+S`) — {{tr:multi_compare.action.quick_save}}: saves immediately with the last export settings, no dialog.
- **Save dialog** — {{tr:multi_compare.action.save}} (toolbar or {{tr:menu.find_action}}): opens the shared image export dialog; see [Export](help://export) for its options.
- **Parity** — export matches the live grid (layout, labels, divider chrome), not a single {{tr:workspace.session_types.image_compare}} split.
- **Crop** — per-slot crop is clipped before composition, so the saved image matches the cropped view.
- **Empty slots** — cells with no loaded image are skipped, not rendered as blanks.
- **Large exports** — saving far above the tested size asks for confirmation first.

### Sessions {#sessions}

- **Payload (v1)** — a session stores slot paths and labels, the layout tree, focus, zoom and pan, plus the divider and label styling.
- **Lazy reopen** — reopening restores paths first and decodes on demand; the visible session fills in, dormant ones fill on activation.
- **Chrome seeding** — a new session starts with the last-used divider and label styling.
