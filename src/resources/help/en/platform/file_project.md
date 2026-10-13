---
description: How images enter a session and how projects bundle them.
icon: folder_open.svg
---
## Files and Projects

Load images into session lists, paste from the clipboard, and open or save a project file that bundles the session layout, the compare settings, and copies of the source images.

### Loading images {#loading-images}

- **Add Img(s) 1** / **Add Img(s) 2** — the add buttons beside the left and right lists open a file picker; pick one or several images for that side.
- **Add images** — in **Multi Compare** a single add button loads images into the grid.
- **Drag and drop** — drop files into the window; they land in the list on the side under the cursor.
- **Paste image from clipboard** (`Ctrl+V`) — the image goes to the active session. A direction overlay appears: click an arrow to choose the side, or press `Esc` to cancel.

:::figure{side=block width=280}
![Paste direction overlay](../../assets/platform/paste_overlay.jpg)
Direction overlay after `Ctrl+V`: click an arrow to send the pasted image to the left or the right list.
:::

### Lists {#lists}

- In **Image Compare**, the left and right lists are independent. The list-manager panel lets you reorder, rate, rename, inspect the path, open properties, and remove images — see [Comparison](help://workspace.image_compare.comparison).
- In **Multi Compare**, images are dropped into individual slots instead of two lists — see [Multi Compare](help://workspace.multi_compare.overview).

Each session has its own tab; see [Tabs](help://platform.tabs).

### Projects {#projects}

A project file (`.imgsli`) keeps a whole workspace in one portable file: the open sessions, their compare settings, and copies of the source images.

- **Open Project** — on the **File** menu, `Ctrl+Shift+O`, or **Find Action**. The active tab takes the file's name, and the project restores the sessions, the compare settings (divider, diff, magnifier, and related features), and the embedded image copies.
- **Save Project** — `Shift+S` writes the current file. When no file exists yet, **Save Project As…** opens instead. Saving also retargets the file name when the tab was renamed.
- **Save Project As…** — `Ctrl+Shift+S` suggests the renamed tab name, otherwise **Untitled**.
- **What the file contains** — a ZIP archive: `project.json` with the sessions, and a `media/` folder holding an embedded copy of each image.
- **If a source is missing** — when a listed path no longer exists, the project still saves; that image is left out and a warning names it.
- **What is not saved** — the theme, language, and hotkeys stay in the application settings; they are not part of the project file.

### Double-click a project on Windows {#windows-file-association}

On Windows the installer associates `.imgsli` with Improve ImgSLI, so double-clicking a project opens it and the file shows the application's document icon. Packaged builds also register the association on startup.

If Properties still shows "Choose application", pick Improve ImgSLI once, or run the app with `--register-file-types` to register the association again.
