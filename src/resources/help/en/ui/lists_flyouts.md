## Lists and Panels

Dropdowns open in-window panels over the main window. Work inside the panel, then dismiss with an outside click or `Esc`. Gestures are covered in [Buttons and Controls](help://ui.buttons); filename label styling in [Comparison](help://comparison).

### List manager {#list-manager}

In a {{tr:workspace.session_types.image_compare}} session each side has a list dropdown. A click opens that side’s list-manager panel (rows, ratings, drag). The panel stays closed if the list is empty. Click the same dropdown again, click outside, or pick a row to close it. While rename or properties is open, the panel does not dismiss on focus loss.

:::figure{side=center width=320}
![List manager panel](ui/placeholder.png)
List dropdown → list-manager panel (placeholder).
:::

### Scroll {#scroll-lists}

- **Dropdown wheel** — steps the current image on that side without opening the panel.
- **Canvas wheel** — steps the side under the cursor; `Shift` + wheel steps both sides. Full rules: [Comparison → Scroll through images](help://comparison#scroll-images).
- **Rating wheel** — changes the row score only, not the current index.

### Rows {#rows}

- **Select** — click a row to make it current; the panel closes and the canvas updates.
- **Reorder** — drag within one list.
- **Move across lists** — drag a row outside the single panel to expand double mode, then drop on the other list.
- **Path tip** — hover a truncated name for the full path.

### Rating {#rating}

Each row has a rating chip. Use minus / plus, or scroll the chip, without leaving the panel.

### Context menu {#context-menu}

- **List row** — rename, copy path, properties, or remove.
- **Canvas (current frame)** — same menu plus duplicate; rename is list-only.

Properties opens [Image Properties](help://image_properties).

### Toolbar buttons {#quick-list-actions}

- **Add files** — button beside each dropdown; appends to that side only.
- **Swap** (`X`) — short click exchanges the current pair; long-press swaps both lists.
- **Remove** — short click drops the current frame on that side; long-press clears the whole list for that side.

### Loading {#loading}

Drag-and-drop onto the window asks which list should receive the files. `Ctrl+V` pastes a clipboard image and may show a side overlay — see [Files and Projects](help://file_management).

### Label settings panel {#toolbar-flyouts}

{{tr:image_compare.action.text_settings}} (or right-click {{tr:image_compare.action.file_names}}) opens a panel for size, weight, colors, and placement. Close with `Esc` or an outside click. Divider color uses a picker, not a panel — see [Comparison](help://comparison). Magnifier option panels: [Magnifier](help://magnifier).

:::figure{side=left width=280}
![Label settings panel](ui/placeholder.png)
{{tr:image_compare.action.text_settings}} (placeholder).
:::

### {{tr:workspace.session_types.multi_compare}} {#multi-compare}

A {{tr:workspace.session_types.multi_compare}} session has no dual-list panel — images go into grid slots. Label text settings still open a panel (without the placement radios from {{tr:workspace.session_types.image_compare}}). Details: [{{tr:workspace.session_types.multi_compare}}](help://multi_compare).
