# Settings plugin

App-wide settings host: the Settings dialog, `SettingsManager` disk
persistence, language/font/UI-mode mutation, and canvas-feature setting
bindings. This is the single owner of the persisted settings store used
across the whole app.

Source: `src/plugins/settings/`. Plugin system: [PLUGINS.md](../PLUGINS.md).
Persistence details: [SETTINGS_PERSISTENCE.md](../SETTINGS_PERSISTENCE.md).

## Wiring

`@plugin(name="settings", startup_tier="bootstrap")`, implements
`IServicePlugin` (and `IUIPlugin`/`IControllablePlugin`-style command surface
via `get_controller` / `handle_command`).

- `initialize(context)` builds `SettingsController` from `context.store` +
  `context.settings_manager` + `context.event_bus`, then subscribes
  `SettingsChangeLanguageEvent` / `SettingsApplyFontSettingsEvent` and binds
  canvas-feature settings events for every registered tab type.
- `register_canvas_feature_bindings(tab_registry, tab_types=...)` reads each
  tab's canvas feature settings-event bindings (`get_canvas_registry(tab_type)
  .get_feature_settings_event_bindings()`) and forwards them to
  `SettingsController.execute_canvas_feature_command`. Called again for
  `multi_compare` in the deferred tier.
- `get_qss_paths()` → `resources/settings.qss`.

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
