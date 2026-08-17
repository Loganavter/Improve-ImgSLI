# App-wide plugins (`src/plugins/`)

Per-plugin documentation for the app-wide plugins living under `src/plugins/`.
These are host-level features (settings, export, help, …) — they run across
every workspace tab. For the plugin *system* itself (lifecycle, discovery,
`@plugin` contract, inventory) see [PLUGINS.md](../PLUGINS.md). For tab-owned
plugins (comparison, session_picker, multi_compare, image_gallery,
video_editor) see each tab's own docs under `src/tabs/<tab>/docs/`.

## Inventory

| Plugin | Tier | Doc | One-liner |
|---|---|:-:|---|
| `settings` | bootstrap | [settings.md](settings.md) | Settings dialog, `SettingsManager` disk persistence, canvas-feature setting bindings |
| `layout` | bootstrap | [layout.md](layout.md) | UI-mode subscriber; applies `ui_mode` to the tab-provided layout manager |
| `onboarding` | bootstrap | [onboarding.md](onboarding.md) | First-run UI-mode picker mounted on the startup stack |
| `export` | deferred (10) | [export.md](export.md) | Still/video export dialog, recording/clipboard commands, GPU warm-up |
| `help` | deferred | [help.md](help.md) | In-app hierarchical illustrated manual (hub/tree) |
| `image_properties` | deferred | [image_properties.md](image_properties.md) | Image metadata dialog + `build_image_properties` |

Tier/order semantics: see [PLUGINS.md](../PLUGINS.md#discovery).

## Files (common pattern)

A plugin under `src/plugins/<name>/` typically has:

| File | Role |
|---|---|
| `plugin.py` | `@plugin(...)` class; wiring site |
| `controller.py` | command surface (`IControllablePlugin`) + EventBus subscriptions |
| `dialog.py` | `ThemedDialog` subclass owning dialog lifecycle |
| `events.py` | frozen dataclasses published on EventBus |
| `services/`, `application_service.py`, `manager.py` | domain/services logic |
| `actions.py` | Find Action contributions (see [ACTIONS.md](../ACTIONS.md)) |
| `resources/<name>.qss` | plugin-owned stylesheet (via `get_qss_paths`) |

Not every plugin has all of these — see the per-plugin docs.
