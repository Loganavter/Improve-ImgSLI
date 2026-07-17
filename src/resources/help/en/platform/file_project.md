## Files and Projects

Load images into session lists, paste from the clipboard, and open or save project files that remember session layout and paths — not pixel data.

### Loading images {#loading-images}

- **Add files** — use the side add buttons (or {{tr:menu.find_action}}) to pick one or more files.
- **Drag-and-drop** — drop into the window and choose which list or {{tr:workspace.session_types.multi_compare}} slot receives them.
- **Paste** (`Ctrl+V`) — clipboard image; when the direction overlay appears, arrows or `WASD` pick the side, `Esc` cancels.

:::figure{side=right width=280}
![Paste direction overlay](ui/placeholder.png)
`Ctrl+V` — paste direction overlay (placeholder).
:::

### Lists {#lists}

- **{{tr:workspace.session_types.image_compare}}** — left and right lists are independent; the list-manager panel covers reorder, rate, rename, path, properties, remove — [Lists and Panels](help://ui.lists_flyouts).
- **{{tr:workspace.session_types.multi_compare}}** — per-slot drops instead of dual lists — [{{tr:workspace.session_types.multi_compare}}](help://multi_compare).

### Projects {#projects}

- **Open / save** — `.imgsli-project` from the File menu (or {{tr:menu.find_action}}) restores layout and file paths.
- **References only** — moving or deleting sources breaks reopen until you re-link; pixel buffers are not embedded.
