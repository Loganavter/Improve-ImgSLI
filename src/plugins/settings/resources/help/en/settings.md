## Settings

Application behavior in one dialog: built-in pages plus sections contributed by workspace tabs, such as image-compare analysis and the gallery AI settings. Tab sections stay visible regardless of the active session.

### Open Settings {#open-settings}

- **Menu** — {{tr:menu.settings}} (`Ctrl+,`).
- **Toolbar** — the gear button.
- **Find Action** — `Ctrl+Shift+P` ({{tr:menu.find_action}}) and a page name ({{tr:settings.general}}, {{tr:settings.appearance}}, {{tr:settings.keyboard}}, …).
- **{{tr:action.palette.learn_more}}** — opens the help topic for a settings action, when one exists.

### Search inside Settings {#search}

A search field sits above the sidebar. Each matching section appears as one row, however deep the match sits (a control name, a group title, any language). Activating a row opens that section with the matched options highlighted. `Esc` clears the search and restores the full sidebar. The sidebar is resizable.

### General {#general}

- **{{tr:label.language}}** — en / ru / zh / pt_BR.
- **{{tr:label.theme}}** — auto / light / dark.
- **{{tr:settings.system_notifications}}** — OS-level notification toggle.
- **{{tr:settings.enable_debug_logging}}** — verbose logs for troubleshooting.

### Appearance {#interface}

- **{{tr:settings.ui_mode}}** — {{tr:settings.ui_mode_beginner}} / {{tr:settings.ui_mode_advanced}} / {{tr:settings.ui_mode_expert}} radios; beginner is the default and the first-run choice lands here.
- **{{tr:settings.ui_font}}** — builtin, system default, or custom family.
- **{{tr:settings.ui_scale}}** — interface scale slider (0.5–2.5).
- **Limits** — related caps such as max displayed name length.

### Performance {#performance}

- **{{tr:settings.render_backend_label}}** — the offered backends depend on the platform; switching may need a restart.

### {{tr:workspace.session_types.image_compare}} {#image_compare}

Image-compare options, always available:

- **Interpolation** — resampling quality for zoom and magnifier.
- **{{tr:settings.optimize_magnifier_movement}}** — smoother lens motion, with its interpolation method on the same row.
- **{{tr:settings.magnifier_intersection_highlight}}** — highlights where lenses overlap; **{{tr:settings.magnifier_auto_color_new_instances}}** gives new lenses distinct colors.
- **{{tr:image_compare.settings.recording_fps}}** — capture rate for the [Video Editor](help://video).
- **{{tr:settings.autocrop_black_borders_on_load}}** — trim black borders when loading.
- **{{tr:settings.autocalculate_psnr}}** / **{{tr:settings.autocalculate_ssim}}** — automatic metric readout, off by default.

### {{tr:image_gallery.settings.ai_title}} {#image-gallery-ai}

AI requests in [Image Gallery](help://gallery_triage) use the settings below. A request needs the AI switch on, an API key, and a model; setting only the key is not enough.

- **{{tr:image_gallery.settings.enable_ai}}** — turns the AI features on or off.
- **{{tr:image_gallery.settings.base_url}}** — address of the AI service.
- **{{tr:image_gallery.settings.api_key}}** — credential for that service.
- **{{tr:image_gallery.settings.model_name}}** — model used for requests.

### Keyboard {#keyboard}

- **Remap** — shortcuts group by owner: platform / {{tr:workspace.session_types.image_compare}} / {{tr:workspace.session_types.multi_compare}}.
- **Reset** — one shortcut or all.
- **Fixed** — canvas `WASD` and `Space` stay fixed — see [Hotkeys](help://hotkeys).
