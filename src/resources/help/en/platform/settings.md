## Settings

Settings are grouped by job — general, appearance, performance, analysis, and keyboard — so you change one concern at a time.

### Open Settings {#open-settings}

- **Menu / gear** — {{tr:menu.settings}} or the toolbar gear.
- **Find Action** — `Ctrl+Shift+P` ({{tr:menu.find_action}}) and type a page name ({{tr:settings.general}}, {{tr:settings.appearance}}, {{tr:settings.keyboard}}, …).
- **{{tr:action.palette.learn_more}}** — on a settings action jumps here with the matching anchor when tagged.

### General {#general}

- **{{tr:label.language}}** — en / ru / zh / pt_BR.
- **{{tr:label.theme}}** — auto / light / dark.
- **{{tr:settings.system_notifications}}** — desktop OS notifications after save (in-app toast is separate).
- **{{tr:settings.enable_debug_logging}}** — verbose logs for troubleshooting.

### Appearance {#interface}

- **{{tr:settings.ui_mode}}** — {{tr:settings.ui_mode_beginner}} / {{tr:settings.ui_mode_advanced}} / {{tr:settings.ui_mode_expert}}.
- **{{tr:settings.ui_font}}** — builtin, system, or custom family.
- **Limits** — related caps such as max displayed name length.

### Performance {#performance}

- **{{tr:settings.render_backend_label}}** — platform-dependent; may need a restart.
- **{{tr:settings.display_cache_resolution}}** — caps the main preview size; magnifier and export still use originals ({{tr:workspace.session_types.image_compare}}).
- **Interpolation** — zoom / magnifier / laser resampling quality.
- **{{tr:settings.optimize_magnifier_movement}}** — smoother lens motion (and its interpolation method on the same page).
- **{{tr:settings.magnifier_intersection_highlight}}** — highlight where lenses overlap.
- **{{tr:settings.magnifier_auto_color_new_instances}}** — distinct colors for new lenses.
- **{{tr:settings.recording_fps}}** — capture rate for [Video Editor](help://video).

### Analysis {#analysis}

Only for {{tr:workspace.session_types.image_compare}}:

- **{{tr:settings.autocrop_black_borders_on_load}}** — trim black borders when loading.
- **Auto {{tr:ui.psnr}} / {{tr:ui.ssim}}** — under the canvas (off by default).

Open this page while an {{tr:workspace.session_types.image_compare}} session is active if the tab contributes the section.

### Keyboard {#keyboard}

- **Remap** — search actions; chords per platform / {{tr:workspace.session_types.image_compare}} / {{tr:workspace.session_types.multi_compare}} groups.
- **Reset** — one shortcut or all.
- **Fixed** — canvas `WASD` and `Space` stay fixed — see [Hotkeys](help://hotkeys).
