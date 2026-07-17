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
└── help/                       # host Help shell (tree.json + ui/platform bodies; tab topics under tabs/<tab>/resources/help — see HELP_SYSTEM.md)
```

Plus per-plugin, per-tab, and per-canvas-feature i18n roots:
```
src/plugins/<name>/resources/i18n/{en,ru,...}/<plugin>.json
src/tabs/<tab>/resources/i18n/{en,ru,...}/*.json
src/tabs/image_compare/canvas/features/<name>/resources/i18n/{en,ru,...}/*.json
```

Tab-owned icon assets (see [Icons](#icons) and [tabs/package-structure.md](tabs/package-structure.md)):
```
src/tabs/<tab>/icons.py                         # Icon enum + get_icon()
src/tabs/<tab>/resources/icons/{light,dark}/*.svg
src/tabs/icon_loader.py                         # shared tab_icon_resolver helper
```

These are auto-discovered and registered as additional i18n roots — see "Bootstrap" below. Note that `plugins/` and `tabs/` are scanned the same way: several top-level app features (e.g. `image_compare`, `multi_compare`, `session_picker`) live under `src/tabs/` rather than `src/plugins/`, but both packages are plugins from the discovery system's point of view (see [PLUGINS.md](PLUGINS.md)).

## Translation pipeline

The translation system lives in the external toolkit (`sli_ui_toolkit.i18n`); ImgSLI re-exports it via `src/resources/translations.py`.

| Path | Role |
|---|---|
| `sli_ui_toolkit/i18n.py` | `TranslationManager` singleton, `tr()`, `translatable_text()`, `translation_events` |
| `src/resources/translations.py` | Facade: configures root, exposes `tr`, `add_i18n_root`, `emit_language_changed` |
| `src/core/plugin_system/registry.py:48` | Auto-registers each `plugins/<name>/` and `tabs/<name>/` package's `resources/i18n/` as an i18n root during discovery |
| `src/ui/canvas_infra/scene/widget_registry.py:80` | Same for canvas features (`get_canvas_widget_features`) |

## Bootstrap

```python
# src/resources/translations.py — runs at import
configure_i18n(i18n_root=Path(resource_path("resources/i18n")))
```

Then per-plugin / per-tab / per-feature directories are merged in via `add_i18n_root(path)` during the discovery walk:

- plugins and tabs: `PluginRegistry` / `discovery_scan.iter_plugin_entry_points()` → `add_i18n_root(<plugin>/resources/i18n)` per entry point
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
| Used only by one tab | `src/tabs/<tab>/resources/i18n/<lang>/*.json` |
| Used only by one canvas feature | `src/tabs/image_compare/canvas/features/<name>/resources/i18n/<lang>/*.json` |
| Cross-cutting (errors, common buttons) | `src/resources/i18n/<lang>/core/*.json` |

Don't add app-wide keys to a plugin's or tab's i18n root — they won't be found if the plugin/tab is disabled.

## Adding a new language

1. Create `src/resources/i18n/<lang>/` (mirroring `en/`'s file structure).
2. For each plugin, tab, and canvas feature you want translated, add `<lang>/` next to the existing `en/` directory.
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

Icons are split between **host/app-shell** assets and **tab-owned** assets.
Tabs must not import `ui.icon_manager` — they vendor whatever SVG they need
under their own `resources/icons/` (see [tabs/isolation.md](tabs/isolation.md)).

### App / host icons

Stored under `src/resources/assets/icons/{light,dark}/` (SVG preferred).
The app window icon lives at `src/resources/icons/icon.png`.

Loaded through `src/ui/icon_manager.py`:

| Symbol | Role |
|---|---|
| `AppIcon` | Enum for host-only icons: window chrome, workspace tabs bar, settings dialog sidebar (built-in sections), shared host widgets |
| `get_app_icon()` | Resolves `AppIcon` via the app `IconService`; also delegates `tabs.*.icons.Icon` enums to each tab's `get_icon()` so toolkit `Button(Icon.X)` works without tab code touching the host resolver |

Use the enum (or a tab `Icon` enum — see below), not a raw path string.

Current `AppIcon` members are intentionally narrow — shell/settings only
(`SETTINGS`, `ADD`, `CLOSE`, window controls, …). Comparison-toolbar icons
live in the tab packages.

### Tab icons

Each tab that needs toolbar/UI icons provides:

```
src/tabs/<tab>/
    icons.py                          # class Icon(Enum) + get_icon = tab_icon_resolver(...)
    resources/icons/
        light/*.svg
        dark/*.svg
```

Pattern (`tabs/image_compare/icons.py` is the reference):

```python
from enum import Enum
from pathlib import Path
from tabs.icon_loader import tab_icon_resolver

_TAB_DIR = Path(__file__).resolve().parent
get_icon = tab_icon_resolver(_TAB_DIR)

class Icon(Enum):
    PHOTO = "photo_icon.svg"
    MAGNIFIER = "magnifier.svg"
    # ...
```

`tab_icon_resolver()` (`tabs/icon_loader.py`) wraps toolkit `IconService`
with `icons_relative_path="resources/icons"` relative to the tab package dir.

Usage inside tab code:

```python
from tabs.image_compare.icons import Icon, get_icon

Button(Icon.MAGNIFIER, toggle=True)          # toolkit resolves via get_app_icon delegation
pixmap = get_icon(Icon.VERTICAL_SPLIT).pixmap(18, 18)  # direct QIcon when needed
```

**Session-type icons** (new-session picker cards): implement
`TabContract.icon` on the tab class; other tabs fetch them via the host service
`context.call_service("get_tab_icon", session_type)` — do not hardcode another
tab's icon enum in `session_picker`.

**Settings sections contributed by a tab** may pass a resolved `QIcon`
(`get_icon(Icon.HIGHLIGHT_DIFFERENCES)`) into `SettingsSection.icon` when the
icon is tab-specific; built-in settings pages continue to use `AppIcon`.

### Adding a new tab icon

1. Copy `light/` and `dark/` SVGs into `src/tabs/<tab>/resources/icons/`.
2. Add a member to `tabs/<tab>/icons.py` `Icon` enum (filename must match).
3. Use `Icon.MEMBER` in tab UI code — never `AppIcon` or a path string.
4. Contract test `tests/contracts/test_tab_icons.py` verifies every enum member
   has both theme variants and resolves to a non-null `QIcon`.

### Plugins

Host plugins under `src/plugins/` still use `AppIcon` / `get_app_icon` for
their dialogs and settings pages. They do not yet have a per-plugin icon root
analogous to tabs; add one only when a plugin needs icons no other owner uses.

## Help content

Host shell: `src/resources/help/tree.json` + `en|ru/ui/…` + `en|ru/platform/…`
+ shared `assets/`. Tab topics: `src/tabs/<tab>/resources/help/<lang>/` via
`notify_all("contribute_help", …)`. Chrome labels in bodies use `{{tr:…}}` —
authoring rules in [HELP_SYSTEM.md § Language keys](HELP_SYSTEM.md#language-keys-tr).

## See also

- [THEMING.md](THEMING.md) — palette & QSS pipeline
- [tabs/index.md](tabs/index.md) — tab-owned resources & isolation rules
- [HELP_SYSTEM.md](HELP_SYSTEM.md) — Help shell, contribution, and authoring
- [PLUGINS.md](PLUGINS.md) — plugin i18n auto-discovery in `PluginRegistry`
- `sli-ui-toolkit/i18n.py` — full TranslationManager source
