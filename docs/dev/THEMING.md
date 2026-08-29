# Theming

Centralised palette pipeline. Lives in the external `sli-ui-toolkit` package (`ThemeManager` singleton); ImgSLI registers its palette at startup. Application QSS was **retired on 2026-08-29** — all visual output goes through tokens painted in code (see "QSS is retired" below).

## Files

| Path | Role |
|---|---|
| `sli_ui_toolkit/ui/managers/theme_manager.py` | `ThemeManager` singleton — palette store + `theme_changed` signal (QSS machinery still exists in the toolkit but the app registers no QSS) |
| `src/core/theme.py` | `load_themes()` — parses `resources/themes.json` into two `dict[str, QColor]` palettes |
| `src/resources/themes.json` | The actual color tokens (light + dark) |
| `src/ui/theming.py` | Thin facade: `install_application_theme`, `polish_themed_dialog`, `resolve_theme_color` |
| `src/core/bootstrap.py:_configure_theme_manager` | Wires the palettes into the singleton at startup |

## Architecture

```
themes.json  →  load_themes() → (light, dark) palettes
                     │
                     ▼
          ThemeManager.register_palettes(light, dark)
                     │
                     ▼
          ThemeManager.apply_theme_to_app(app)
                     │            │
                     ▼            ▼
              QPalette set   empty stylesheet (no QSS registered)
                     │
                     ▼
          ThemeManager.theme_changed.emit()
                     │
                     ▼
       widgets connected to theme_changed → re-read tokens, repaint
```

## ThemeManager API (singleton)

```python
ThemeManager.get_instance()                  # always returns the same instance

# Registration (do once, at bootstrap):
register_palettes(light: dict, dark: dict | None)
register_qss_path(path: str)                 # toolkit API — unused by the app since QSS retirement

# Reads (anywhere, anytime):
get_color(token: str) -> QColor              # token = key from themes.json; "#000000" if missing
try_get_color(token: str) -> QColor | None   # None if missing
is_dark() -> bool
get_current_theme() -> "light" | "dark"

# Writes:
set_theme(name: str, app=None)               # "light" / "dark"; applies palette, emits theme_changed
set_color(token: str, color: QColor)         # runtime override (settings UI uses this)
apply_theme_to_app(app: QApplication)        # re-apply QPalette; called on theme change
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

## QSS is retired

Application QSS was fully removed on 2026-08-29 (171 rules across 7 files
deleted; the last files were `app.qss` and `editor.qss`). The painter
pipeline (`paintEvent` + token reads) owns every surface:

- Qt only honors QSS backgrounds/borders on widgets whose class is exactly
  `QWidget` (as a top level) or on stock widgets (`QFrame`/`QScrollArea`/…).
  Custom `QWidget` subclasses never get `WA_StyledBackground`, so QSS rules
  on toolkit widgets silently no-op and the widget falls back to the QPalette
  `Window` role — which hosts keep darker than the dialog surface token
  (near-black in the dark theme). That was the Settings sidebar "black
  substrate" bug, fixed by painting surfaces from tokens instead. Verified
  2026-08-29.
- Surfaces paint themselves from `dialog.background`: toolkit
  `IconListWidget`, `SidebarDialogShell`'s content area (`_SurfaceWidget`),
  and app `ThemedDialog` (every app dialog paints its own surface).
  App-side containers use `ThemedSurface`/`ThemedBackgroundContainer`
  (`src/ui/widgets/themed_surface.py`) or a small `ThemedWidget` subclass
  with a `paintEvent` fill. The same explicit-`paintEvent` pattern is the
  documented fix for any future "this surface is black" bug (see "Known Qt
  quirk" below).
- Stock `QScrollArea`s paint the raw `Window` role; scroll surfaces use the
  toolkit `SurfaceScrollArea` (Help dialog content, Find Action list,
  video-editor tab panes and timeline): token fill by default
  (`dialog.background` — a widget-level `background-color` resolved from the
  token, cascades to the viewport and content and survives `QStyle::polish`
  at `show()`, same mechanism as the toolkit's
  `ScrollableDialogPage._apply_dialog_surface`), or transparent mode
  (`surface_token=None`) where the host pane already paints the surface
  (video-editor tabs). `ui.theming.tint_scroll_surface` remains as the
  documented app facade for hosts that cannot swap classes. Toolkit
  `HelpDocumentView` also paints its own surface from `dialog.background`
  (used standalone in the Image Properties dialog).
- `bootstrap.py` registers no QSS; `Plugin.get_qss_paths()` was removed.
  The toolkit `ThemeManager` still ships the QSS template machinery
  (`register_qss_path`, `_scale_qss_px`) — dormant, kept for other hosts.

The hard rule (also in AGENTS.md and the toolkit's `DESIGN_LANGUAGE.md`):
**never use QSS (`setStyleSheet`) to style toolkit widgets — the painter
pipeline owns all visual output.** If you must add a stylesheet rule today,
prefer a widget-level `setStyleSheet` on the specific widget over app-wide
QSS.

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

## Theme switch performance

`ThemeManager.set_theme` (toolkit ≥ 3.1.5) freezes top-level widget updates
for the whole theme apply **and** the `theme_changed` fan-out, then issues one
`update()` pass. Labels (toolkit ≥ 3.1.6) only recolor on theme flip.

Toolkit ≥ 3.1.7: `set_theme(..., await_ripples=True)` (default) postpones that
blocking apply until any active button ripple finishes, so the press wave is
not frozen mid-frame. Improve-ImgSLI does **not** set a process-wide
`default_defer_click`; only heavy actions opt in with
`set_defer_click(DEFER_CLICK_AWAIT_RIPPLE)` (Settings Apply, session-picker
create cards). Tune duration via
`set_ripple_duration_ms`. Top-levels that still host an active ripple are
skipped by `suspend_widget_updates`.

## Language switch performance

Language Apply is a text fan-out (`language_changed` → `translatable_*`), not
QSS. Toolkit ≥ 3.1.8: workspace-page bindings use `defer_when_hidden=True` so
stacked-away tabs (Image Compare while the session picker is up, and vice
versa) skip updates until the next `Show`. Presenter extras
(`do_update_*` / flyouts) are gated the same way and flushed via
`flush_stale_workspace_language` on session switch. Do not call
`reapply_button_styles` from the language path — polish is theme-owned.

App-side: `TabRegistry.apply_appearance` updates only the **visible**
workspace page; hidden tabs flush on the next session switch. Session-picker
icon SVG re-resolve is deferred off the hot path. Do not re-apply fonts from
`MainWindowAppearance.on_theme_changed` — fonts are theme-independent.

## Extension recipe — adding a color token

1. Add the key under both `"light"` and `"dark"` in `src/resources/themes.json`:
   ```json
   "light": { ..., "my_section.accent": "#4F8AF7" },
   "dark":  { ..., "my_section.accent": "#7AA6F8" }
   ```
2. In the widget: `resolve_theme_color(ThemeManager.get_instance(), "my_section.accent")` (app code uses `try_resolve_theme_color` from `src/ui/theming.py` — bare `get_color` outside theme-infra files is forbidden by contract tests).
3. Restart — palettes are loaded once at import.

There is no QSS recipe anymore: surfaces are painted in `paintEvent` from
tokens (see `ThemedSurface` / the QSS-retirement section above).

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
`src/ui/widgets/themed_surface.py::ThemedBackgroundContainer` pairs the
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

Full details and confirmed call sites: `docs/dev/KNOWN_BUGS.md` in
`improve-imgsli-internal-docs` (private).

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
- `docs/dev/KNOWN_BUGS.md` in `improve-imgsli-internal-docs` (private) — Qt/platform quirks, including the palette/autoFillBackground issue above
- `sli-ui-toolkit/docs/dev/DESIGN_LANGUAGE.md` — toolkit-side conventions