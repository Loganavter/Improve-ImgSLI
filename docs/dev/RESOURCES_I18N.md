# Resources & i18n

How translations, icons, themes, and other static assets are organised and loaded.

## Layout

```
src/resources/
├── i18n/                       # App-wide translations
│   ├── README.md
│   ├── en/                     # fallback — required
│   │   └── core/app.json
│   ├── ru/
│   ├── pt_BR/
│   └── zh/
├── themes.json                 # color palettes (see THEMING.md)
├── styles/app.qss              # app-wide QSS
├── icons/                      # SVG/PNG icon assets
├── assets/                     # other static binaries
└── help/                       # help pages (markdown per language)
```

Plus per-plugin and per-feature i18n roots:
```
src/plugins/<name>/resources/i18n/{en,ru,...}/<plugin>.json
src/tabs/image_compare/canvas/features/<name>/resources/i18n/{en,ru,...}/*.json
```

These are auto-discovered and registered as additional i18n roots — see "Plugin & feature i18n" below.

## Translation pipeline

The translation system lives in the external toolkit (`sli_ui_toolkit.i18n`); ImgSLI re-exports it via `src/resources/translations.py`.

| Path | Role |
|---|---|
| `sli_ui_toolkit/i18n.py` | `TranslationManager` singleton, `tr()`, `translatable_text()`, `translation_events` |
| `src/resources/translations.py` | Facade: configures root, exposes `tr`, `add_i18n_root`, `emit_language_changed` |
| `src/core/plugin_system/registry.py:46` | Auto-registers each plugin's `resources/i18n/` as an i18n root during discovery |
| `src/ui/canvas_infra/scene/widget_registry.py:52` | Same for canvas features |

## Bootstrap

```python
# src/resources/translations.py — runs at import
configure_i18n(i18n_root=Path(resource_path("resources/i18n")))
```

Then per-plugin / per-feature directories are merged in via `add_i18n_root(path)` during the discovery walk:

- plugins: `PluginRegistry._scan_package` → `add_i18n_root(<plugin>/resources/i18n)`
- canvas features: `widget_registry.get_canvas_widget_features` → `add_i18n_root(<feature>/resources/i18n)`

## JSON format & key resolution

Each language directory contains arbitrary JSON files (any names, any nesting). All files under one language are deep-merged into a single nested dict. Sample:

```
src/resources/i18n/en/core/app.json:
{
  "app": { "name": "Improve ImgSLI" }
}

src/plugins/export/resources/i18n/en/export.json:
{
  "export": { "dialog.title": "Export", "btn.save": "Save" }
}
```

Lookup uses **dotted keys**: `tr("app.name")`, `tr("export.btn.save")`.

Loading order (later wins on conflict, but `warn_on_override=False` for non-app roots so toolkit/plugins extend silently):
1. App `en/` (fallback)
2. App `<lang>/` (overrides)
3. For each registered extra root: `en/` then `<lang>/`

## The `tr()` API

```python
from resources.translations import tr

tr("export.btn.save")                       # current language
tr("export.btn.save", language="ru")        # specific language (no global state change)
tr("export.btn.save", default="Save")       # custom fallback if key missing
tr("error.with_value", name="foo")          # str.format(**kwargs) on the template
```

Missing keys return the key itself (or `default` if given). They also log a warning the first time.

## Language switching

```python
from resources.translations import emit_language_changed, get_current_language, translation_events

emit_language_changed("ru")                 # loads pack, sets current, emits language_changed signal
current = get_current_language(default="en")

# Widgets subscribe:
translation_events().language_changed.connect(my_callback)  # callback(lang_code) → None
```

The store setting `SettingsState.language` is the source of truth. The settings plugin calls `emit_language_changed` when it changes.

## `translatable_text` helpers — auto-rebinding widgets

Instead of manually wiring `language_changed → widget.setText(...)`:

```python
from sli_ui_toolkit.i18n import translatable_text, translatable_tooltip, translatable_placeholder

translatable_text(my_label, "settings.section.title")
translatable_tooltip(my_button, "settings.section.tooltip")
translatable_placeholder(my_lineedit, "settings.field.placeholder")
```

These call `setText`/`setToolTip` immediately, connect to `language_changed`, and **auto-disconnect when the widget is destroyed** (via `widget.destroyed` signal + shiboken validity check). No lifetime management.

For arbitrary callbacks (e.g. when one key feeds multiple widgets):
```python
translatable_callback(widget, lambda lang: refresh_my_panel(widget, lang))
```

## Picking where a key lives

| Key reference | File |
|---|---|
| Used only by one plugin | `src/plugins/<name>/resources/i18n/<lang>/<plugin>.json` |
| Used only by one canvas feature | `src/tabs/image_compare/canvas/features/<name>/resources/i18n/<lang>/*.json` |
| Cross-cutting (errors, common buttons) | `src/resources/i18n/<lang>/core/*.json` |

Don't add app-wide keys to a plugin's i18n root — they won't be found if the plugin is disabled.

## Adding a new language

1. Create `src/resources/i18n/<lang>/` (mirroring `en/`'s file structure).
2. For each plugin and feature you want translated, add `<lang>/` next to the existing `en/` directory.
3. Missing keys fall back to `en` silently.
4. Register the language in the settings UI's language list (`src/plugins/settings/...`).

## Adding a new translation key

1. Pick the right JSON file (see "Picking where a key lives" above).
2. Add the dotted path; create nested objects as needed:
   ```json
   { "foo": { "bar": { "title": "Hello" } } }
   ```
3. Add the same key to **all** language files (or at least `en/`).
4. Use it: `tr("foo.bar.title")`. For dynamic widget binding: `translatable_text(widget, "foo.bar.title")`.
5. After saving, restart — translations are loaded lazily but cached.

## Icons

Stored under `src/resources/icons/` (SVG preferred, themed via QSS color tokens where possible). Loaded through `src/ui/icon_manager.py:AppIcon` (an enum-like registry — `AppIcon.DIVIDER_HIDDEN`, etc.). Use the enum, not a raw path string.

## Help content

Per-language markdown under `src/resources/help/<lang>/`. See [HELP_WIDGET.md](HELP_WIDGET.md) for the rendering side.

## See also

- [THEMING.md](THEMING.md) — palette & QSS pipeline
- [HELP_WIDGET.md](HELP_WIDGET.md) — help content rendering
- [PLUGINS.md](PLUGINS.md) — plugin i18n auto-discovery in `PluginRegistry`
- `sli-ui-toolkit/i18n.py` — full TranslationManager source
