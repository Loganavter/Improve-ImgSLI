## Settings

Application behavior in one dialog: built-in pages plus sections contributed by workspace tabs (image-compare analysis, gallery AI credentials). Tab sections stay visible regardless of the active session.

### Open Settings {#open-settings}

- **Menu** — {{tr:menu.settings}} (`Ctrl+,`).
- **Toolbar** — the gear button.
- **Find Action** — `Ctrl+Shift+P` ({{tr:menu.find_action}}) and a page name ({{tr:settings.general}}, {{tr:settings.appearance}}, {{tr:settings.keyboard}}, …).
- **{{tr:action.palette.learn_more}}** — on a settings action opens the matching anchor when tagged.

### Search inside Settings {#search}

A search field sits above the sidebar: matches list one row per section, no matter how deep inside it the match sits (a control name, a group title, any language). Activating a row opens that section with the matched options pulsed. `Esc` clears the search and restores the full sidebar. The sidebar is resizable.

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

- **Interpolation** — zoom / magnifier / laser resampling quality.
- **{{tr:settings.optimize_magnifier_movement}}** — smoother lens motion, with its interpolation method on the same row.
- **{{tr:settings.magnifier_intersection_highlight}}** — highlight where lenses overlap.
- **{{tr:settings.magnifier_auto_color_new_instances}}** — distinct colors for new lenses.
- **{{tr:image_compare.settings.recording_fps}}** — capture rate for the [Video Editor](help://video).
- **{{tr:settings.autocrop_black_borders_on_load}}** — trim black borders when loading.
- **Auto {{tr:ui.psnr}} / {{tr:ui.ssim}}** — automatic metric readout, off by default.

### Keyboard {#keyboard}

- **Remap** — shortcuts group by owner: platform / {{tr:workspace.session_types.image_compare}} / {{tr:workspace.session_types.multi_compare}}.
- **Reset** — one shortcut or all.
- **Fixed** — canvas `WASD` and `Space` stay fixed — see [Hotkeys](help://hotkeys).
