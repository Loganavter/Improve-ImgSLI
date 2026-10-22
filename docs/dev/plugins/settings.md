# Settings plugin

App-wide settings host: the Settings dialog, `SettingsManager` disk
persistence, language/font/UI-mode mutation, and canvas-feature setting
bindings. This is the single owner of the persisted settings store used
across the whole app.

Source: `src/plugins/settings/`. Plugin system: [PLUGINS.md](../PLUGINS.md).
Persistence details: [SETTINGS_PERSISTENCE.md](../SETTINGS_PERSISTENCE.md).

## Wiring

`@plugin(name="settings", startup_tier="bootstrap")`;
`class SettingsPlugin(Plugin, IServicePlugin)` exposes a command surface through
`get_controller`, `get_service` and `handle_command` (the `IControllablePlugin`
method set; the class does not specialise that ABC, and `IUIPlugin` no longer
exists — `core/plugin_system/interfaces.py` defines only `IControllablePlugin`,
`IServicePlugin`, `ISessionPlugin`).

- `initialize(context)` builds `SettingsController` from `context.store` +
  `context.settings_manager` + `context.event_bus`, then subscribes
  `SettingsChangeLanguageEvent` / `SettingsApplyFontSettingsEvent` and binds
  canvas-feature settings events for every registered tab type.
- `register_canvas_feature_bindings(tab_registry, tab_types=...)` reads each
  tab's canvas feature settings-event bindings (`get_canvas_registry(tab_type)
  .get_feature_settings_event_bindings()`) and forwards them to
  `SettingsController.execute_canvas_feature_command`. Called again for
  `multi_compare` in the deferred tier.
- `get_controller()` / `handle_command` — command surface (see
  [PLUGINS.md](../PLUGINS.md)). No plugin QSS: the dialog surface is painted
  from the `dialog.background` token in `ThemedDialog.paintEvent`.

## Key modules

| Module | Role |
|---|---|
| `manager.py` | `SettingsManager` — `QSettings` wrapper with corrupt-file `.backup` healing, load/save caller tracing, per-key value funnel |
| `controller.py` | `SettingsController` — language / font / UI-mode mutation, canvas-feature command/alias routing |
| `mutations.py` | `SettingsMutationService` — set settings through `store` + `SettingsManager` with notify |
| `notifier.py` | `SettingsUpdateNotifier` — core-update + UI-mode + event-bus notifications |
| `application_service.py` | `SettingsApplicationService` — app-level apply flows (e.g. deferred scale resync) |
| `dialog.py` | `SettingsDialog(ThemedDialog)` — sectioned settings UI with sidebar, in-dialog search, sync from store |
| `dialog_shell.py`, `dialog_context.py`, `member_resolve.py`, `search.py`, `translations.py` | dialog construction, member lookup, search, i18n |
| `pages/` | per-category pages: `general`, `interface`, `analysis`, `performance`, `keyboard` |
| `registry.py` | `SettingsRegistry` / `SettingsSection` — section catalog + tab contributions (`ensure_tab_settings_contributions`) |
| `canvas_feature_gateway.py` | `execute_canvas_feature_command` / `execute_canvas_feature_alias` — route setting changes into canvas feature commands |
| `events.py` | frozen events: `SettingsChangeLanguageEvent`, `SettingsApplyFontSettingsEvent`, `SettingsUIModeChangedEvent`, `SettingsAnalysisMetricsRequestedEvent` |

## Events (EventBus)

- `SettingsChangeLanguageEvent(lang_code)` — controller changes language,
  calls `emit_language_changed`, notifies window shell.
- `SettingsApplyFontSettingsEvent(size, weight, color, bg_color, draw_bg,
  placement, alpha)` — applies font settings; captures a recorder frame when
  recording.
- `SettingsUIModeChangedEvent(ui_mode)` — consumed by the `layout` plugin.
- `SettingsAnalysisMetricsRequestedEvent(payload)` — analysis metrics request.

## Persistence

`SettingsManager` is the write funnel for persisted values; the Store mirrors
them for runtime. See [SETTINGS_PERSISTENCE.md](../SETTINGS_PERSISTENCE.md)
for the file, load/save paths, apply flow, and the corrupt-backup heuristic.

## Help ownership

`help.py` carries exactly one symbol, `HELP_MOUNT = "platform.settings"` — the
fs-scanned help tree mounts this package's pages there, so the section owns page
`platform.settings` (moved byte-identical from host; the `#general` /
`#interface` / `#performance` anchors live in the page body). Pack:
`resources/help/` bodies ×4 + one figure (`settings.md` references
`../assets/settings_general.png`); `settings.*` i18n keys live in
`resources/i18n/<lang>/settings.json` (moved from the host pack).

The former `build_help_plugin_contribution()` (`owner_plugin="settings"`,
attach `platform`) was removed in `c8231456` with the rest of the contribution
layer.
