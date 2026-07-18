## Files and Projects

Load images into session lists, paste from the clipboard, and open or save portable project files that bundle session layout, compare settings, and copies of the source images.

### Loading images {#loading-images}

- **Add files** — use the side add buttons (or {{tr:menu.find_action}}) to pick one or more files.
- **Drag-and-drop** — drop into the window and choose which list or {{tr:workspace.session_types.multi_compare}} slot receives them.
- **Paste** (`Ctrl+V`) — clipboard image; when the direction overlay appears, arrows or `WASD` pick the side, `Esc` cancels.

:::figure{side=block width=280}
![Paste direction overlay]({{img:platform.file_project.paste_overlay}})
`Ctrl+V` — paste direction overlay.
:::

### Lists {#lists}

- **{{tr:workspace.session_types.image_compare}}** — left and right lists are independent; the list-manager panel covers reorder, rate, rename, path, properties, remove — [Lists and Panels](help://ui.lists_flyouts).
- **{{tr:workspace.session_types.multi_compare}}** — per-slot drops instead of dual lists — [{{tr:workspace.session_types.multi_compare}}](help://multi_compare).

### Projects {#projects}

- **Open / save** — `.imgsli` from the File menu (`Ctrl+Shift+O` / `Shift+S` / `Ctrl+Shift+S`, or {{tr:menu.find_action}}): **Save** writes the current file (or opens **Save As** when none yet); **Save As** suggests a renamed tab title when the active tab is custom, otherwise {{tr:menu.project_untitled}}. **Save** also retargets the file basename when the tab was renamed. Opening a project names the active tab after the file. Restores workspace sessions, compare settings (split, diff, magnifier, and related features), and embedded image copies.
- **Portable package** — the file is a ZIP: session JSON plus a `media/` folder with byte-copies of the originals (not re-encoded pixel buffers).
- **Missing sources on save** — if a listed path no longer exists, the project still saves; that image is omitted and you are warned.
- **App preferences** — theme, language, and hotkeys stay in application settings; they are not part of the project file.
