---
description: Look up a shortcut or remap the ones you use.
icon: enter.svg
---
## Hotkeys

Below are the default chords. Most action shortcuts can be remapped in **Settings** → **Keyboard**; the canvas keys `WASD` / `QE`, the arrow keys, `Space`, and `+` / `-` are fixed and cannot be remapped.

:::figure{side=block width=100%}
![Keyboard settings](../../assets/platform/settings_keyboard.png)
**Settings → Keyboard**: every Platform action with its chord and a **Reset** button; one group per tab follows below.
:::

### Discover first {#discover}

`Ctrl+Shift+P` and part of a name are faster than scanning the list: **Find Action** runs the matching action or opens **Learn more** for the illustrated topic. `F1` opens the help topic for the focused control.

### Platform {#platform}

- `Ctrl+,` — **Settings**
- `Ctrl+F1` — **Show Help**
- `Ctrl+N` — **New Session** (opens the **Session Picker**)
- `Ctrl+Tab` / `Ctrl+Shift+Tab` — next / previous session
- `Ctrl+Shift+P` — **Find Action**
- `Ctrl+V` — **Paste image from clipboard**
- `Ctrl+Shift+O` / `Shift+S` / `Ctrl+Shift+S` — **Open Project** / **Save Project** / **Save Project As…** (`.blinktable`)
- `Ctrl+Q` — **Quit**

Menu labels follow the language you select. Custom shortcuts are set in **Settings** → **Keyboard**, in the platform group.

### Image Compare {#image-compare}

- `M` / `F` — **Toggle Magnifier** / **Freeze Magnifier**
- `N` / `L` — **Filename Overlay** / **Divider Visibility**
- `H` / `C` — **Difference Mode** / **Channel Mode**
- `X` — **Swap Images**
- `R` / `Ctrl+E` — **Record Video** / **Video Editor**
- `Ctrl+S` — **Quick Save**
- `WASD` / `QE` — move the magnifier / change its spacing (fixed)
- `Shift+Space` — preview one side in combined mode (fixed)
- `←↑↓→` / `+` / `-` — pan / zoom (fixed)

Details: [Comparison](help://workspace.image_compare.comparison), [Magnifier](help://workspace.image_compare.magnifier), [Video Editor](help://workspace.image_compare.video).

### Multi Compare {#multi-compare}

- `Ctrl+O` — **Add images**
- `D` — **Grid Visibility**
- `Ctrl+S` — **Quick Save**
- `Esc` — leave slot focus
- `←↑↓→` / `+` / `-` — pan / zoom (fixed)

See [Multi Compare](help://workspace.multi_compare.overview).

### Image Gallery {#image-gallery}

- `Space` / `Delete` — remove the selected images from the grid; the files stay on disk.

See [Triage and Review](help://workspace.image_gallery.triage).

### Video editor window {#video-editor}

While the editor window is open:

- `Space` — play or pause
- `Ctrl+Z` / `Ctrl+Y` — undo / redo
- `Delete` / `Backspace` — remove the selected range

Full encode workflow: [Video Editor](help://workspace.image_compare.video).

### Keyboard navigation {#keyboard-navigation}

- `F1` — opens the help topic for the focused control; a control with no resolvable topic falls back to **Find Action** (with the matching action highlighted when there is one).
- In **Find Action** (`Ctrl+Shift+P`): `↑` / `↓` move the selection, `Enter` runs it, `Ctrl+Enter` opens **Learn more**, `Esc` closes the list.
- In the Multi Compare overview, slot focus follows the pointer: a click toggles single-image focus, `Esc` exits it. Arrow keys pan the canvas instead of moving focus between slots.
- In the session picker, arrow keys move focus between cards and `Enter` opens the focused card, same as clicking it.
- There is no `Tab` traversal between canvas slots: focus follows the pointer, and the keyboard drives actions through **Find Action**.
