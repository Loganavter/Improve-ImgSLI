## Settings

Settings collects every application option in one dialog: built-in pages such as **General** and **Appearance**, plus sections contributed by tabs, such as the **Image Compare** options and the **Image Gallery — AI** settings. Tab sections stay visible regardless of the active session.

### Open Settings {#open-settings}

- **Menu** — **File** → **Settings** (`Ctrl+,`).
- **Find Action** — `Ctrl+Shift+P`, then a page name (General, Appearance, Keyboard, …).
- **Learn more** — opens the help topic for a setting when one is available.

### Search inside Settings {#search}

A search field sits above the sidebar. Each matching section appears as a single row, however deep the match is (a control name, a group title, any language). Activating a row opens that section with the matches highlighted. `Esc` clears the search and restores the full sidebar.

### General {#general}

- **Language** — chooses the interface language: en / ru / zh / pt_BR.
- **Theme** — auto / light / dark.
- **System notifications** — turns OS-level notifications on or off.
- **Enable debug logging** — writes verbose logs for troubleshooting.

### Appearance {#interface}

- **UI Mode** — **Beginner**, **Advanced**, or **Expert**; **Beginner** is the default and the first-run pick lands here.
- **UI Font** — built-in, system default, or a custom family.
- **Interface Scale** — slider that resizes the whole interface (0.5–2.5).
- **Maximum Name Length (UI)** — caps the length of a displayed name.

### Performance {#performance}

- **Backend** — rendering backend. The choices depend on the platform, and switching may require a restart.

### Image Compare {#image_compare}

Image-compare options, always available:

- **Zoom Interpolation** — sets the resampling quality for zoom.
- **Magnifier movement** — makes lens motion smoother; its interpolation method sits on the same row.
- **Red highlight for overlapping magnifiers** — while you drag a magnifier, the part of its capture ring hidden behind other magnifiers is highlighted. **Auto-color new magnifiers** gives each new lens a distinct color.
- **Recording FPS** — capture rate for the [Video Editor](help://workspace.image_compare.video).
- **Auto-crop black borders on load** — trims black borders when an image is loaded.
- **Auto-calculate PSNR** / **Auto-calculate SSIM** — show the metric automatically; off by default.

### Image Gallery — AI {#image-gallery-ai}

AI requests in [Image Gallery](help://workspace.image_gallery.triage) use the settings below. A request needs the AI switch on, an API key, and a model; setting only the key is not enough.

- **Enable AI image analysis** — turns the AI features on or off.
- **API base URL** — address of the AI service.
- **API key** — credential for that service.
- **Model name** — the model the AI uses for requests.

### Keyboard {#keyboard}

- **Remap** — groups shortcuts by owner: platform / Image Compare / Multi Compare.
- **Reset** — resets one shortcut or all of them.
- **Fixed** — canvas `WASD` and `Space` cannot be remapped — see [Hotkeys](help://platform.hotkeys).
