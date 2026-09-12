## Hotkeys

Default chords below. Remap most action shortcuts under {{tr:menu.settings}} → {{tr:settings.keyboard}}. Canvas `WASD`, arrow, `Space` movement and `+`/`-` zoom stay fixed and are not remappable.

### Discover first {#discover}

Press `Ctrl+Shift+P` and type a name before memorizing a list. Run the action from the palette, or open {{tr:action.palette.learn_more}} when you need the illustrated topic. F1 can pulse the matching action when focus is tagged.

### Platform {#platform}

- `Ctrl+,` — Settings
- `Ctrl+F1` — Help
- `Ctrl+N` — Session picker / new session
- `Ctrl+Tab` / `Ctrl+Shift+Tab` — Next / previous workspace session
- `Ctrl+Shift+P` — {{tr:menu.find_action}}
- `Ctrl+V` — Paste image
- `Ctrl+Shift+O` / `Shift+S` / `Ctrl+Shift+S` — Open / save / save project as (`.imgsli`)
- `Ctrl+Q` — Quit

Exact labels follow your language pack; remap under Settings → Keyboard → platform group.

### {{tr:workspace.session_types.image_compare}} {#image-compare}

- `M` / `F` — Magnifier / freeze
- `N` / `D` — Filename labels / divider visibility
- `H` / `C` — Difference mode / channel mode
- `X` — Swap
- `R` / `Ctrl+E` — Record / Video Editor
- `Ctrl+S` — Quick save
- `WASD` / `QE` / `Space` — Magnifier move / spacing / side preview (fixed)
- `←↑↓→` / `+` / `-` — Pan / zoom (fixed)

Details: [Comparison](help://comparison), [Magnifier](help://magnifier), [Video Editor](help://video).

### {{tr:workspace.session_types.multi_compare}} {#multi-compare}

- `Ctrl+O` — Add images (when bound)
- `D` — Grid visibility
- `Ctrl+S` — Quick save
- `Esc` — Exit slot focus
- `←↑↓→` / `+` / `-` — Pan / zoom (fixed)

See [{{tr:workspace.session_types.multi_compare}}](help://multi_compare).

### Video editor window {#video-editor}

While the editor is open: `Space` play/pause, `Ctrl+Z` / `Ctrl+Y` undo/redo, `Delete` / `Backspace` remove selection. Full encode workflow: [Video Editor](help://video).

### Keyboard navigation {#keyboard-navigation}

- `F1` — contextual help for the focused control. When focus is tagged to an action, the {{tr:menu.find_action}} result pulses the match; otherwise the palette opens pre-filtered by topic.
- In {{tr:menu.find_action}} (`Ctrl+Shift+P`): `↑` / `↓` move the selection, `Enter` runs it, `Ctrl+Enter` opens {{tr:action.palette.learn_more}}, `Esc` closes the palette.
- In the {{tr:workspace.session_types.multi_compare}} overview, slot focus follows the pointer: a click toggles single-image focus, `Esc` exits it. Arrow keys pan the canvas instead of moving focus between slots.
- In the session picker, arrow keys move focus between cards and `Enter` opens the focused card, same as clicking it.
- There is no `Tab` traversal between canvas slots: focus follows the pointer, and the keyboard drives actions through the palette.