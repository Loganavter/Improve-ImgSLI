## Settings

Settings are grouped by job — general, appearance, performance, and keyboard — plus {{tr:workspace.session_types.image_compare}}, the only workspace tab contributing a settings section today. Tab sections are always visible, no matter which session is active, so tab options have a permanent home.

### Open Settings {#open-settings}

- **Menu / gear** — {{tr:menu.settings}} or the toolbar gear.
- **Find Action** — `Ctrl+Shift+P` ({{tr:menu.find_action}}) and type a page name ({{tr:settings.general}}, {{tr:settings.appearance}}, {{tr:settings.keyboard}}, …).
- **{{tr:action.palette.learn_more}}** — on a settings action jumps here with the matching anchor when tagged.

### Search inside Settings {#search}

A search field sits above the sidebar: type anything and the matching sections are listed — one row per section, no matter how deep inside it the match is (a control name, a group title, any language). Activate a row to open that section: the matched options inside it light up (if several match at the same level, all of them). The query matches in every UI language, like {{tr:menu.find_action}}. `Esc` clears the search and restores the full sidebar. The sidebar itself is resizable — drag the divider between it and the settings content.

### General {#general}

- **{{tr:label.language}}** — en / ru / zh / pt_BR.
- **{{tr:label.theme}}** — auto / light / dark.
- **{{tr:settings.system_notifications}}** — desktop OS notifications after save (in-app toast is separate).
- **{{tr:settings.enable_debug_logging}}** — verbose logs for troubleshooting.

### Appearance {#interface}

- **{{tr:settings.ui_mode}}** — {{tr:settings.ui_mode_beginner}} / {{tr:settings.ui_mode_advanced}} / {{tr:settings.ui_mode_expert}}.
- **{{tr:settings.ui_font}}** — builtin, system, or custom family.
- **{{tr:settings.ui_scale}}** — interface scale independent of the system display scale (0.5–2.5); applies live — controls, fonts, icons, and spacing resize immediately.
- **Limits** — related caps such as max displayed name length.

### Performance {#performance}

- **{{tr:settings.render_backend_label}}** — platform-dependent; may need a restart.

### {{tr:workspace.session_types.image_compare}} {#image_compare}

Image-compare specific options live on their own section, always available:

- **Interpolation** — zoom / magnifier / laser resampling quality.
- **{{tr:settings.optimize_magnifier_movement}}** — smoother lens motion (and its interpolation method on the same page).
- **{{tr:settings.magnifier_intersection_highlight}}** — highlight where lenses overlap.
- **{{tr:settings.magnifier_auto_color_new_instances}}** — distinct colors for new lenses.
- **{{tr:settings.recording_fps}}** — capture rate for [Video Editor](help://video).
- **{{tr:settings.autocrop_black_borders_on_load}}** — trim black borders when loading.
- **Auto {{tr:ui.psnr}} / {{tr:ui.ssim}}** — under the canvas (off by default).

### Keyboard {#keyboard}

- **Remap** — search actions; chords per platform / {{tr:workspace.session_types.image_compare}} / {{tr:workspace.session_types.multi_compare}} groups.
- **Reset** — one shortcut or all.
- **Fixed** — canvas `WASD` and `Space` stay fixed — see [Hotkeys](help://hotkeys).
