## Hotkeys

The list below gives the default chords. Most action shortcuts can be remapped in **Settings** → **Keyboard**. The canvas `WASD`, arrow, and `Space` movement keys and the `+` / `-` zoom stay fixed and cannot be remapped.

### Discover first {#discover}

Press `Ctrl+Shift+P` and type part of a name instead of memorizing the list: **Find Action** runs the matching action or opens **Learn more** for the illustrated topic. `F1` highlights the matching action when the focused control is tied to it.

### Platform {#platform}

- `Ctrl+,` — Settings
- `Ctrl+F1` — Help
- `Ctrl+N` — Session picker / new session
- `Ctrl+Tab` / `Ctrl+Shift+Tab` — Next / previous workspace session
- `Ctrl+Shift+P` — Find Action
- `Ctrl+V` — Paste image
- `Ctrl+Shift+O` / `Shift+S` / `Ctrl+Shift+S` — Open / save / save project as (`.imgsli`)
- `Ctrl+Q` — Quit

Menu labels follow the language you select. Custom shortcuts are set in **Settings** → **Keyboard**, in the platform group.

### Image Compare {#image-compare}

- `M` / `F` — toggle the magnifier / freeze it
- `N` / `D` — toggle the filename overlay / hide the divider
- `H` / `C` — switch the difference mode / switch the channel mode
- `X` — swap the two images
- `R` / `Ctrl+E` — start recording / open the **Video Editor**
- `Ctrl+S` — **Quick Save**
- `WASD` / `QE` — move the magnifier / change its spacing (fixed)
- `Shift+Space` — preview one side in combined mode (fixed)
- `←↑↓→` / `+` / `-` — pan / zoom (fixed)

Details: [Comparison](help://workspace.image_compare.comparison), [Magnifier](help://workspace.image_compare.magnifier), [Video Editor](help://workspace.image_compare.video).

### Multi Compare {#multi-compare}

- `Ctrl+O` — add more images to the grid
- `D` — toggle the grid visibility
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
- `Delete` / `Backspace` — trim to the selection

Full encode workflow: [Video Editor](help://workspace.image_compare.video).

### Keyboard navigation {#keyboard-navigation}

- `F1` — contextual help for the focused control. When the focused control is tied to an action, the **Find Action** result highlights the match; otherwise **Find Action** opens pre-filtered by topic.
- In **Find Action** (`Ctrl+Shift+P`): `↑` / `↓` move the selection, `Enter` runs it, `Ctrl+Enter` opens **Learn more**, `Esc` closes the list.
- In the Multi Compare overview, slot focus follows the pointer: a click toggles single-image focus, `Esc` exits it. Arrow keys pan the canvas instead of moving focus between slots.
- In the session picker, arrow keys move focus between cards and `Enter` opens the focused card, same as clicking it.
- There is no `Tab` traversal between canvas slots: focus follows the pointer, and the keyboard drives actions through **Find Action**.
