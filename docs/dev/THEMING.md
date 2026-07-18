# Theming & QSS

Centralised palette + QSS pipeline. Lives in the external `sli-ui-toolkit` package (`ThemeManager` singleton); ImgSLI registers its palette and QSS files at startup.

## Files

| Path | Role |
|---|---|
| `sli_ui_toolkit/ui/managers/theme_manager.py` | `ThemeManager` singleton — palette store + QSS pipeline + `theme_changed` signal |
| `src/core/theme.py` | `load_themes()` — parses `resources/themes.json` into two `dict[str, QColor]` palettes |
| `src/resources/themes.json` | The actual color tokens (light + dark) |
| `src/resources/styles/app.qss` | App-wide QSS template (with `{token}` placeholders) |
| `src/ui/theming.py` | Thin facade: `install_application_theme`, `polish_themed_dialog`, `resolve_theme_color` |
| `src/core/bootstrap.py:_configure_theme_manager` | Wires palettes + QSS paths into the singleton at startup |

## Architecture

```
themes.json  →  load_themes() → (light, dark) palettes
                     │
                     ▼
          ThemeManager.register_palettes(light, dark)
          ThemeManager.register_qss_path("base.qss")
          ThemeManager.register_qss_path("widgets.qss")
          ThemeManager.register_qss_path("app.qss")
                     │
                     ▼
          ThemeManager.apply_theme_to_app(app)
                     │            │
                     ▼            ▼
              QPalette set   QSS rendered with current palette tokens
                     │
                     ▼
          ThemeManager.theme_changed.emit()
                     │
                     ▼
       widgets connected to theme_changed → re-style themselves
```

## ThemeManager API (singleton)

```python
ThemeManager.get_instance()                  # always returns the same instance

# Registration (do once, at bootstrap):
register_palettes(light: dict, dark: dict | None)
register_qss_path(path: str)                 # registered in order; later wins on conflict

# Reads (anywhere, anytime):
get_color(token: str) -> QColor              # token = key from themes.json; "#000000" if missing
try_get_color(token: str) -> QColor | None   # None if missing
is_dark() -> bool
get_current_theme() -> "light" | "dark"

# Writes:
set_theme(name: str, app=None)               # "light" / "dark"; rebuilds QSS, emits theme_changed
set_color(token: str, color: QColor)         # runtime override (settings UI uses this)
apply_theme_to_app(app: QApplication)        # re-apply QSS+QPalette; called on theme change
apply_theme_to_dialog(dialog: QWidget)       # for standalone modal dialogs

# Signal:
theme_changed: Signal()                       # no payload; subscribers re-read get_color()
```

## Palettes (`src/resources/themes.json`)

Two flat dicts of `{token_name: hex_color}`. Conventions:
- Semantic names (`button.background`, `flyout.border`), not visual names (`gray-200`).
- Same key set for both light and dark — if a key is missing from dark, theme switching looks broken at runtime.
- Add new tokens here, never as inline `#xxxxxx` in widgets.

Loaded once at module import by `core/theme.py:load_themes()` and exposed as `LIGHT_THEME_PALETTE`, `DARK_THEME_PALETTE`.

## QSS

QSS files are concatenated in registration order with a separator (`/* --- NEW FILE --- */`) into `_qss_template`. On `apply_theme_to_app`, the template is rendered against the current palette: tokens like `palette(button.background)` (or whatever placeholder convention the toolkit uses — check `theme_manager._render_template`) are substituted.

Registered at bootstrap in `src/core/bootstrap.py:_configure_theme_manager`:
- `shared_toolkit/ui/resources/styles/base.qss`
- `shared_toolkit/ui/resources/styles/widgets.qss`
- `resources/styles/app.qss`

Plus each plugin contributes via `Plugin.get_qss_paths()` — see [PLUGINS.md](PLUGINS.md).

## Connecting a widget to theme changes

Pattern used everywhere in the toolkit:

```python
class MyWidget(QWidget):
    def __init__(self, ...):
        ...
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._apply_styles)
        self._apply_styles()              # initial paint

    def _apply_styles(self):
        bg = self.theme_manager.get_color("my_widget.background")
        self.setStyleSheet(f"background: {bg.name()};")
```

Do **not** cache `get_color()` results — re-read on every `theme_changed` so palette overrides via `set_color` take effect.

For QPainter-based custom widgets, call `theme_manager.get_color(...)` inside `paintEvent` (or invalidate via `self.update()` in `_apply_styles`).

## Extension recipe — adding a color token

1. Add the key under both `"light"` and `"dark"` in `src/resources/themes.json`:
   ```json
   "light": { ..., "my_section.accent": "#4F8AF7" },
   "dark":  { ..., "my_section.accent": "#7AA6F8" }
   ```
2. In the widget: `bg = ThemeManager.get_instance().get_color("my_section.accent")`.
3. If used from QSS, add a rule in `resources/styles/app.qss` using the toolkit's token placeholder syntax (look at existing entries for the format).
4. Restart — palettes are loaded once at import.

## Extension recipe — adding a new QSS file

For a plugin:
```python
def get_qss_paths(self) -> tuple[str, ...]:
    return (self.plugin_resource_path("resources/styles/my_plugin.qss"),)
```
The discovery loop in `bootstrap._initialize_plugins` registers them automatically.

For shared/app QSS: add `theme_manager.register_qss_path(...)` in `bootstrap._configure_theme_manager` — keep that file as the single registration point.

## Common gotchas

- **New widget looks unstyled**: it's not connected to `theme_changed`, or you cached the QColor in `__init__`.
- **Dark mode is wrong**: check that the token exists in *both* palettes.
- **QSS edit not picked up**: the template is built once at startup; call `theme_manager.apply_theme_to_app(app)` (or restart) to rebuild.
- **Want a per-dialog override**: use `polish_themed_dialog(theme_manager, dialog)` from `src/ui/theming.py`.
- **Dialog / label text stuck on the old theme after switch**: with an application stylesheet, `style().unpolish()` / `polish()` *after* `setPalette()` restores the previous palette. `ThemeManager.apply_theme_to_dialog` polishes first, then sets the palette. Toolkit `Label` also re-applies `apply_text_color` on `ParentChange` / `StyleChange` because reparent can wipe `WA_SetPalette` text colors. Do not put `color:` on `QLabel` in QSS — use palette / `apply_text_color` so `setFont` / `UiFont` still work.

## Repaint on theme change: the `ThemedWidget` mixin

Theme repaint for app chrome and dialogs goes through `ThemedWidget`
(`sli_ui_toolkit.ui.widgets.themed.ThemedWidget`, exported from
`sli_ui_toolkit.widgets`). It subscribes to `theme_changed` in `__init__`
and calls `on_theme_changed()` (override this instead of connecting your
own signal; default implementation just calls `self.update()`).
`src/ui/widgets/themed_container.py::ThemedBackgroundContainer` pairs the
mixin with a plain `QWidget` for chrome bars/containers that need to paint
their own background from a theme token, instead of relying on inheriting
a painted background from an ancestor.

App surfaces on `ThemedWidget` / `ThemedBackgroundContainer` include
`MultiCompareToolbar`, `MultiCompareFooter`, `ImageCompareWidget`,
`SessionPickerWidget`, and image_compare chrome widgets
(`selection_widget`, `checkbox_widget`, `footer_info_widget`,
`edit_layout_widget`, `save_buttons_widget` in
`tabs/image_compare/ui/layout.py`).

App dialogs inherit `ThemedDialog`
(`shared_toolkit/ui/themed_dialog.py`): settings, image_properties, export,
video_editor. Call `mark_theme_ui_ready()` after building the widget tree;
override `on_dialog_theme_changed()` (not `on_theme_changed()`) for
dialog-specific extras such as sidebar icon refresh or preview palette. Help
uses toolkit `MarkdownHelpDialog`'s own `theme_changed` wiring until that
class moves to `ThemedWidget`.

Startup surfaces (`_startup_placeholder`, `_startup_cover`, `StartupPlaceholder`)
use `ThemedSurface` (`ui/widgets/themed_surface.py`) — same explicit-`paintEvent`
pattern as `ThemedBackgroundContainer`, keyed on `label.image.background`.
`MainWindowAppearance.update_image_label_background` only forwards to tab
`apply_appearance` hooks. QRhi canvas backgrounds go through
`apply_qrhi_theme_background` in the same module.

Still on hand-written `theme_changed.connect(self.update)` (fold in when
touched, not as a dedicated sweep): toolkit `MarkdownHelpDialog` and the ~20
existing toolkit widgets that already self-subscribe.

## Known Qt quirk: don't repaint backgrounds via `setPalette()` + `setAutoFillBackground`

The "implicit" Qt repaint path — `setPalette()` + `setAutoFillBackground(True)`,
relying on Qt's own background-paint step before `paintEvent` — is
unreliable in this app: affected widgets visibly "warm up," taking 2-3
repeated theme switches before they start repainting correctly, and a
single switch does not reliably repaint. Confirmed via `QWidget.grab()`
that the stale pixels are in the actual rendered pixmap, not a
presentation/compositor artifact. Root Qt-internal mechanism is still
unknown. Fix: override `paintEvent()` and paint the background explicitly
from a `QColor` cached in `on_theme_changed()`:

```python
def paintEvent(self, event) -> None:
    painter = QPainter(self)
    painter.fillRect(self.rect(), self._bg_color)
    painter.end()

def on_theme_changed(self) -> None:
    self._bg_color = QColor(resolve_theme_color(self._theme_manager, "Window"))
    super().on_theme_changed()  # still calls self.update()
```

Full details and confirmed call sites: [KNOWN_BUGS.md](KNOWN_BUGS.md).

## Known gotcha: icons must resolve lazily, not eagerly

Pass `AppIcon` enum values (or another lazy handle) into widgets rather
than eagerly resolving to a `QIcon` at construction time — eager
resolution freezes the icon at whatever theme was active when the widget
was built, so it never updates on theme switch. (`session_picker` and
Help hub cards had exactly this bug; both refresh via `sync_icons` on
theme change when the icon must stay an eager `QIcon`.)

## See also

- `src/ui/theming.py` — small facade (`install_application_theme`, `polish_themed_dialog`, `resolve_theme_color`)
- [PLUGINS.md](PLUGINS.md) — `get_qss_paths()` plugin contribution hook
- [UI_INSPECTOR.md](UI_INSPECTOR.md) — runtime tool for inspecting which color token a widget resolves to
- [KNOWN_BUGS.md](KNOWN_BUGS.md) — Qt/platform quirks, including the palette/autoFillBackground issue above
- `sli-ui-toolkit/docs/DESIGN_LANGUAGE.md` — toolkit-side conventions
