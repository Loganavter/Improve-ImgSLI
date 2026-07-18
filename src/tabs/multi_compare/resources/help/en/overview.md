## Multi Compare Overview

Compare many images in one session using a layout grid, per-slot drops, and focus mode.

### Open a session {#open-session}

Choose {{tr:workspace.session_types.multi_compare}} in the Session Picker, or run {{tr:action.workspace.new_multi_compare}} from {{tr:menu.find_action}} (`Ctrl+Shift+P`). See also [Workspace Tabs](help://session_picker).

### Layouts and gap splits {#layouts}

- **Grid** — arrange slots; drop files onto a cell or use {{tr:multi_compare.action.add_images}} (`Ctrl+O`).
- **Empty slots** — stay open for new drops.
- **Gap drop** — drop onto a gap between cells to split and create a new cell recursively.
- **Weights** — drag grid dividers to change relative sizes.
- **Layout change** — keeps loaded images where possible.

:::figure{side=block width=320}
![Multi Compare grid]({{img:workspace.multi_compare.overview.layouts}})
{{tr:workspace.session_types.multi_compare}} — grid / gap-drop.
:::

### Focus mode {#focus-mode}

- **Enter** — double-click a slot for full-canvas focus.
- **Exit** — `Esc` returns to the grid.
- **Navigate** — zoom and pan like {{tr:workspace.session_types.image_compare}}; see [Canvas Navigation](help://view_navigation).

### Grid and labels {#grid-and-labels}

- **Visibility** (`D`) — {{tr:multi_compare.action.divider_visible}}.
- **Color / width** — {{tr:multi_compare.action.divider_color}} and {{tr:multi_compare.action.divider_width}}.
- **Label text** — {{tr:multi_compare.action.text_settings}} opens styling (no placement radios from {{tr:workspace.session_types.image_compare}}).

### Slot context menu {#context-menu}

Right-click a slot for per-image actions, including [Image Properties](help://image_properties) (file metadata and slot position) and **Move** (drag ghost → click another workspace tab to start placement like DnD / paste).

### Save and export {#save-and-export}

- **Quick save** (`Ctrl+S`) — {{tr:multi_compare.action.quick_save}}.
- **Save dialog** — {{tr:multi_compare.action.save}} (toolbar or {{tr:menu.find_action}}).
- **Parity** — export matches the live grid (layout, labels, divider chrome), not a single {{tr:workspace.session_types.image_compare}} split.

Search save / export in {{tr:menu.find_action}} while the {{tr:workspace.session_types.multi_compare}} tab is focused.
