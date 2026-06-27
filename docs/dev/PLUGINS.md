# Plugin lifecycle

Each top-level feature (comparison, export, settings, analysis, video_editor, image_properties, help, layout) is a **plugin**: a self-contained module under `src/plugins/<name>/` that registers itself, declares what it contributes, and is initialized through a uniform lifecycle.

This document covers wiring. For canvas-tool plugins (sliders, magnifier, overlays) see [CANVAS_FEATURES.md](CANVAS_FEATURES.md) — a parallel system layered on top.

## Files

| Path | Role |
|---|---|
| `src/core/plugin_system/plugin.py` | `Plugin` ABC, `PluginState` enum |
| `src/core/plugin_system/decorators.py` | `@plugin(name=..., version=...)` |
| `src/core/plugin_system/registry.py` | `PluginRegistry` — discovery via `pkgutil` |
| `src/core/plugin_system/lifecycle.py` | `PluginLifecycleManager` — initialize / activate / deactivate / shutdown loop |
| `src/core/plugin_system/contributions.py` | `PluginDefinitionRegistry` — manifests + capability map |
| `src/core/plugin_system/interfaces.py` | `IControllablePlugin`, `ISessionPlugin` |
| `src/core/plugin_coordinator.py` | `PluginCoordinator` — combines registry, lifecycle, capabilities, session blueprints |
| `src/core/bootstrap.py:_initialize_plugins` | The single wiring site |

## Bootstrap flow (`src/core/bootstrap.py:134`)

```
discover_plugins()                                 # PluginRegistry: scan + instantiate
  └─► PluginDefinitionRegistry.register_plugins    # collect manifests
  └─► PluginCoordinator.register_plugins           # capability map + session blueprints
        └─► PluginLifecycleManager.register
  └─► PluginCoordinator.initialize(context)        # initialize_all → activate_all
        └─► Plugin.initialize(context)
        └─► Plugin.activate()
```

`context` is the live `ApplicationContext` — plugins pull `store`, `event_bus`, `thread_pool` from it (`getattr(context, "store", None)`).

## Discovery (`src/core/plugin_system/registry.py:21`)

`PluginRegistry.discover_plugins()`:

1. Scans `src/plugins/*` and `src/tabs/*` with `pkgutil.iter_modules`.
2. For each sub-package, imports `<package>.<name>.plugin` (if it exists, else the package itself).
3. The `@plugin(...)` decorator (`src/core/plugin_system/decorators.py:7`) appends the class to a module-level `_REGISTERED_PLUGINS` list as a side effect of import.
4. Registry reads `get_registered_plugins()`, instantiates each class once (de-duped by `_plugin_meta["name"]`).
5. Also registers each plugin's `resources/i18n/` directory via `add_i18n_root`.

This is why a plugin only needs the decorator — no central list to edit.

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

- **`IControllablePlugin`** — exposes `handle_command(command, *args, **kwargs)`. Lets `PluginCoordinator.execute_command(plugin_name, command, ...)` dispatch to the plugin without the caller knowing the method name.
- **`ISessionPlugin`** — exposes `get_session_blueprints() -> tuple[SessionBlueprint, ...]`. The coordinator registers these blueprints; the workspace can then create sessions of these types (`create_session(store, session_type)`).

## Reference plugin: `comparison`

Use this as the template for new plugins.

```
src/plugins/comparison/
├── __init__.py
├── plugin.py              # @plugin("comparison") class ComparisonPlugin
├── events.py              # ComparisonUpdateRequestedEvent, ComparisonErrorEvent
├── session_controller.py  # SessionController — orchestrates loading/navigation
└── use_cases/             # loading.py, navigation.py — pure logic
```

`plugin.py` (`src/plugins/comparison/plugin.py:45`):

```python
@plugin(name="comparison", version="1.0")
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

| Plugin | controller | presenter | services / use_cases | events | state |
|---|:-:|:-:|:-:|:-:|:-:|
| comparison | — | (window shell) | session_controller + use_cases/ | ✓ | — |
| export | ✓ | ✓ | services/ExportService | ✓ | ✓ |
| settings | ✓ | ✓ | application_service | ✓ | ✓ |
| analysis | ✓ | — | CachedDiffService, MetricsService | ✓ | ✓ |
| video_editor | — | ✓ | VideoExporterService, Recorder | — | ✓ |
| image_properties | — | — | image_properties/service | — | — |
| help | — | — | — | — | — |
| layout | — | — | layout/manager | — | — |

Patterns:
- **Controller** appears when the plugin exposes commands (buttons / menus / shortcuts) — implements `IControllablePlugin.handle_command`.
- **Presenter** appears for dialog-heavy plugins (settings, export, video_editor) — owns dialog lifecycle.
- **`state.py`** is plugin-private state stored opaquely on viewport (see `_viewport_plugin_state` in [STORE.md](STORE.md#plugin-state-the-escape-hatch)).
- **`events.py`** declares the plugin's outbound events for EventBus.

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

   @plugin(name="my_plugin", version="1.0")
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
6. **Nothing else** — discovery is automatic.

## See also

- [STORE.md](STORE.md) — how plugins read/write app state
- [EVENT_BUS.md](EVENT_BUS.md) — cross-plugin async comms
- [CANVAS_FEATURES.md](CANVAS_FEATURES.md) — the orthogonal plugin system for canvas-tools
- [TAB_CONTRACT.md](TAB_CONTRACT.md) — workspace tab/session interface
