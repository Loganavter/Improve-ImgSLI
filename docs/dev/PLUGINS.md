# Plugin lifecycle

A **plugin** is any module with `@plugin(...)` on a `Plugin` subclass. Discovery scans both `src/plugins/*/plugin.py` and `src/tabs/**/plugin.py` (including nested `tabs/<tab>/plugins/<name>/`). App-wide capabilities live under `src/plugins/`; workspace modes and tab-owned sub-plugins live under `src/tabs/` — see [Inventory](#inventory) below.

**Tab-owned sub-plugins convention:** a plugin with no consumer outside a single tab lives under `src/tabs/<tab_name>/plugins/<plugin_name>/`, mirroring `src/plugins/<name>/` at the tab's own scope, instead of sitting as a bare sibling of the tab's other subpackages (`canvas/`, `ui/`, `services/`, ...). Every `src/tabs/<tab_name>/` gets a `plugins/` package once it has at least one such plugin — do not leave an empty placeholder `plugins/` package for a tab that has none.

This document covers wiring and the live inventory. For canvas-tool plugins (sliders, magnifier, overlays) see [QRHI_CANVAS_FEATURES.md](QRHI_CANVAS_FEATURES.md) — a parallel system layered on top. Tab session/UI contracts are in [tabs/index.md](tabs/index.md).

## Files

| Path | Role |
|---|---|
| `src/core/plugin_system/plugin.py` | `Plugin` ABC, `PluginState` enum |
| `src/core/plugin_system/decorators.py` | `@plugin(name=..., version=...)` |
| `src/core/plugin_system/registry.py` | `PluginRegistry` — staged discovery (`tier=bootstrap|deferred|all`) |
| `src/core/plugin_system/discovery_scan.py` | Filesystem + AST scan for `@plugin(startup_tier=...)` and tab `startup_tier` |
| `src/core/plugin_system/lifecycle.py` | `PluginLifecycleManager` — initialize / activate / deactivate / shutdown loop |
| `src/core/plugin_system/contributions.py` | `PluginDefinitionRegistry` — manifests + capability map |
| `src/core/plugin_system/interfaces.py` | `IControllablePlugin`, `IUIPlugin`, `IServicePlugin`, `ISessionPlugin`, … |
| `src/core/plugin_coordinator.py` | `PluginCoordinator` — combines registry, lifecycle, capabilities, session blueprints |
| `src/core/bootstrap.py:_initialize_plugins` | The single wiring site |

## Bootstrap flow (`src/core/bootstrap.py`)

**Bootstrap tier** (before main window is usable):

```
discover_plugins(tier="bootstrap")                 # manifest import + instantiate
  └─► PluginDefinitionRegistry.register_plugins
  └─► PluginCoordinator.register_plugins
  └─► PluginCoordinator.initialize(context)        # initialize_all → activate_all
```

**Deferred tier** (after `startupVisualReady`, via `QTimer.singleShot(0)`):

```
ApplicationContext.load_deferred_plugins()
  discover_plugins(tier="deferred")                  # video_editor before export
  └─► PluginCoordinator.register_and_start(...)    # init + activate new plugins only
  └─► MainController.attach_deferred_plugins(...)
  └─► SettingsPlugin.register_canvas_feature_bindings(..., tab_types=("multi_compare",))
```

`context` is the live `ApplicationContext` — plugins pull `store`, `event_bus`, `thread_pool`, and (for deferred plugins) `plugin_coordinator` from it.

## Discovery (`src/core/plugin_system/registry.py`)

`PluginRegistry.discover_plugins(*, tier="bootstrap"|"deferred"|"all")`:

| Tier | When | How modules are chosen |
|---|---|---|
| `bootstrap` | `ApplicationContext.initialize()` | AST scan: `@plugin(..., startup_tier="bootstrap")` |
| `deferred` | After first UI reveal | AST scan: `startup_tier="deferred"` (sorted by `startup_order`) |
| `all` | Tests, defensive full load | Import every `plugin.py` found by filesystem scan (incl. nested tab plugins) |

For each imported module:

1. The `@plugin(...)` decorator appends the class to `_REGISTERED_PLUGINS` as a side effect of import.
2. Registry instantiates each newly registered class once (de-duped by `_plugin_meta["name"]`).
3. Each plugin's `resources/i18n/` directory is registered via `add_i18n_root`.

New plugins: add `plugin.py` with `@plugin(name="...", startup_tier="bootstrap"|"deferred")`. No manual manifest — `tests/contracts/test_plugin_startup_tier.py` fails if `startup_tier` is missing or a `plugin.py` is not scanned.

Optional `startup_order: int` on deferred plugins controls init order (e.g. `video_editor=0` before `export=10`).

**Nested tab plugins** (e.g. `tabs/image_compare/plugins/video_editor/plugin.py`) are included in the filesystem scan automatically.

## The `Plugin` contract (`src/core/plugin_system/plugin.py:17`)

```python
class Plugin(ABC):
    context: Any | None
    @abstractmethod
    def initialize(self, context: Any) -> None         # MUST call super().initialize(context)
    def activate(self) -> None
    def deactivate(self) -> None
    def shutdown(self) -> None
    def get_state(self) -> PluginState
    # contribution hooks (optional, all default empty):
    def get_ui_components(self) -> dict[str, Any]
    def get_toolbar_actions(self) -> list
    def get_menu_items(self) -> list
    def get_render_entities(self) -> list
    def get_qss_paths(self) -> tuple[str, ...]
    def get_definition(self) -> Any | None
    def plugin_resource_path(*parts) -> str            # path under the plugin's own directory
```

`PluginState`: `CREATED → INITIALIZED → ACTIVE → INACTIVE → SHUTDOWN`, plus `ERROR` (set by lifecycle manager on exception).

### Optional interfaces (`src/core/plugin_system/interfaces.py`)

- **`IControllablePlugin`** — `get_controller()` + `handle_command(command, ...)`. Lets `PluginCoordinator.execute_command(plugin_name, command, ...)` dispatch without knowing the method name.
- **`IUIPlugin`** — optional toolbar/menu registration hooks (`register_toolbar`, `register_menu`, `get_ui_components`).
- **`IServicePlugin`** — `get_service()` + optional `provides_capability(capability)`.
- **`ISessionPlugin`** — `get_session_blueprints() -> tuple[SessionBlueprint, ...]`. The coordinator registers these; the workspace creates sessions via `create_session(store, session_type)`.
- **`IVideoTrackProvider`** / **`IRenderPlugin`** — specialized contribution hooks (keyframe adapters / render entities).

## Inventory

Live `@plugin` entry points (2026-07-18). Source of truth: filesystem scan of every `plugin.py` under `src/plugins/` and `src/tabs/` (incl. nested `tabs/*/plugins/*/`).

### App-wide (`src/plugins/`)

| Name | Path | Tier | Order | Interfaces | Role |
|---|---|---|:-:|---|---|
| `settings` | `plugins/settings/` | bootstrap | — | `IUIPlugin`, `IServicePlugin` | Settings dialog, `SettingsManager` disk persistence, canvas-feature setting bindings |
| `layout` | `plugins/layout/` | bootstrap | — | — | UI-mode subscriber; obtains `layout_manager` via tab `create_startup_service` (not a local manager module) |
| `onboarding` | `plugins/onboarding/` | bootstrap | — | — | First-run UI-mode picker on the startup stack; reads `SettingsManager.is_first_run` |
| `export` | `plugins/export/` | deferred | 10 | `IControllablePlugin`, `IServicePlugin` | Still/video export dialog, recording/clipboard commands, export QSS |
| `help` | `plugins/help/` | deferred | — | `IUIPlugin`, `IControllablePlugin` | In-app help dialog (hub/tree); see [HELP_SYSTEM.md](HELP_SYSTEM.md) |
| `image_properties` | `plugins/image_properties/` | deferred | — | `IControllablePlugin` | Image metadata dialog + `service.build_image_properties` |

### Tab / session plugins (`src/tabs/`)

| Name | Path | Tier | Order | Interfaces | Role |
|---|---|---|:-:|---|---|
| `comparison` | `tabs/image_compare/` | bootstrap | — | `ISessionPlugin` | Primary two-image compare tab; owns analysis services (`services/analysis/`), session controller, canvas |
| `session_picker` | `tabs/session_picker/` | bootstrap | — | `ISessionPlugin` | Transient "New Tab" session browser / switcher |
| `multi_compare` | `tabs/multi_compare/` | deferred | — | `ISessionPlugin` | Grid multi-image compare tab + `multi_compare.state` slot |
| `video_editor` | `tabs/image_compare/plugins/video_editor/` | deferred | 0 | `ISessionPlugin` | Tab-owned video editor (dialogs, timeline, recorder/export flows); loads before `export` |

There is no `@plugin(name="analysis")`. Diff/metrics/SSIM live under
`tabs/image_compare/services/analysis/` and `shared/analysis/`, constructed by
`ComparisonPlugin`. Opaque `viewport._analysis_plugin_state` is preserved by
the dispatcher — see [STORE.md](STORE.md#plugin-state-the-escape-hatch).

## Reference plugin: `comparison`

Use this as the template for new plugins. Note: `comparison` is also the
`image_compare` tab (see [tabs/index.md](tabs/index.md)), so its plugin
lives under `src/tabs/image_compare/` instead of `src/plugins/`. Discovery
scans both `src/plugins/*` and `src/tabs/*`, so this is still a normal plugin
as far as the plugin system is concerned.

```
src/tabs/image_compare/
├── __init__.py
├── plugin.py              # @plugin("comparison") class ComparisonPlugin
├── tab.py                 # TabContract implementation
├── events/                # ComparisonUpdateRequestedEvent, ComparisonErrorEvent
├── _session_controller.py # SessionController — orchestrates loading/navigation
└── use_cases/             # loading.py, navigation.py — pure logic
```

`plugin.py` (`src/tabs/image_compare/plugin.py`):

```python
@plugin(name="comparison", version="1.0", startup_tier="bootstrap")
class ComparisonPlugin(Plugin, ISessionPlugin):
    def initialize(self, context):
        super().initialize(context)
        self.store = context.store
        self.event_bus = context.event_bus
        self.thread_pool = context.thread_pool
        # construct services here — never in __init__
        self.session_ctrl = SessionController(self.store, ...)

    def bind_window_shell(self, window_shell):
        # called by composer once the main window exists — wire UI-facing refs
        ...

    def get_session_blueprints(self) -> tuple[SessionBlueprint, ...]:
        return (SessionBlueprint(...),)
```

## Plugin layouts in this repo

| Plugin | controller | presenter / dialog | services / use_cases | events | private / session state |
|---|:-:|:-:|:-:|:-:|:-:|
| `comparison` | proxy → session_ctrl | (window shell) | `_session_controller`, `use_cases/`, `services/` (incl. analysis) | ✓ | session slots + `state/` |
| `session_picker` | — | `widget.py` | — | — | transient session blueprint |
| `settings` | ✓ | ✓ (`dialog.py`) | `application_service`, `manager` | ✓ | `store.settings` |
| `layout` | — | — | tab `layout_manager` via registry | — | — |
| `export` | ✓ | ✓ | `services/` | ✓ | — |
| `video_editor` | — | ✓ | `Recorder`, `VideoExporterService`, flows | — | `model.py` (timeline/selection) |
| `multi_compare` | ✓ | (tab UI) | `services/` | — | `multi_compare.state` slot |
| `help` | self (`IControllable`) | `dialog.py` | — | — | — |
| `image_properties` | self (`IControllable`) | `dialog.py` | `service.py` | — | — |
| `onboarding` | — | `overlay.py` / `host.py` | — | — | first-run only; `is_first_run` owned by settings |

Patterns:
- **Controller** appears when the plugin exposes commands (buttons / menus / shortcuts) — typically `IControllablePlugin.handle_command`, or a tab-local controller.
- **Presenter / dialog** appears for dialog-heavy plugins (settings, export, video_editor, help, image_properties) — owns dialog lifecycle.
- **Session state** for tab plugins goes through `ISessionPlugin` blueprints / `state_slots`, not a free-floating `state.py` on every plugin.
- Opaque viewport attrs (`_viewport_plugin_state`, `_analysis_plugin_state`) are the escape hatch documented in [STORE.md](STORE.md#plugin-state-the-escape-hatch) — prefer session slots for new work.
- **`events.py`** declares the plugin's outbound events for EventBus when the plugin publishes cross-component facts.

## Lifecycle invariants

1. **Construct lazily in `initialize`**, not `__init__`. Services need `context.store`, `event_bus`, etc., which only exist at initialize time.
2. **Always call `super().initialize(context)`.** Without it `self.context` is `None` and state stays `CREATED`.
3. **Don't reach into other plugins' internals.** Use `EventBus` for cross-plugin signals; use `PluginCoordinator.execute_command(plugin_name, command, ...)` if you really need a method call. Direct imports between plugins are a smell.
4. **Errors during `_safe_call` set state to `ERROR`** and emit a `PluginEvent(stage="error")` — lifecycle doesn't propagate the exception.
5. **`bind_window_shell` (if present) runs after main-window composition**, not during plugin init. UI-side wiring belongs there.

## Extension recipe — new plugin

1. Create `src/plugins/my_plugin/__init__.py` and `plugin.py`.
2. In `plugin.py`:
   ```python
   from core.plugin_system import Plugin, plugin

   @plugin(name="my_plugin", version="1.0", startup_tier="deferred")
   class MyPlugin(Plugin):
       def initialize(self, context):
           super().initialize(context)
           self.store = context.store
           self.event_bus = context.event_bus
           # subscribe to events, construct services
   ```
3. (Optional) Add `controller.py`, `presenter.py`, `services/`, `events.py`, `state.py` as needed — follow `comparison/` or `export/` as templates depending on whether you need UI commands or dialogs.
4. (Optional) If you contribute QSS, override `get_qss_paths()` and return paths via `self.plugin_resource_path("resources/styles/x.qss")`.
5. (Optional) If your plugin defines a workspace session type, implement `ISessionPlugin.get_session_blueprints()`.
6. **Nothing else** — discovery is automatic; declare `startup_tier` on `@plugin`.

## See also

- [STORE.md](STORE.md) — how plugins read/write app state
- [EVENT_BUS.md](EVENT_BUS.md) — cross-plugin async comms
- [QRHI_CANVAS_FEATURES.md](QRHI_CANVAS_FEATURES.md) — the orthogonal plugin system for canvas-tools
- [tabs/index.md](tabs/index.md) — workspace tab/session interface
