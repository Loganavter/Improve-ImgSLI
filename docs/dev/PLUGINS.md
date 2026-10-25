# Plugin lifecycle

A **plugin** is any module with `@plugin(...)` on a `Plugin` subclass. Discovery scans both `src/plugins/*/plugin.py` and `src/tabs/**/plugin.py` (including nested `tabs/<tab>/plugins/<name>/`). App-wide capabilities live under `src/plugins/`; workspace modes and tab-owned sub-plugins live under `src/tabs/` — see [Inventory](#inventory) below.

**Tab-owned sub-plugins convention:** a plugin with no consumer outside a single tab lives under `src/tabs/<tab_name>/plugins/<plugin_name>/`, mirroring `src/plugins/<name>/` at the tab's own scope, instead of sitting as a bare sibling of the tab's other subpackages (`canvas/`, `ui/`, `services/`, ...). Every `src/tabs/<tab_name>/` gets a `plugins/` package once it has at least one such plugin — do not leave an empty placeholder `plugins/` package for a tab that has none.

This document covers wiring and the live inventory. For canvas-tool plugins (sliders, magnifier, overlays) see [rendering/index.md](rendering/index.md) — a parallel system layered on top. Tab session/UI contracts are in [tabs/index.md](tabs/index.md).

## Files

| Path | Role |
|---|---|
| `src/core/plugin_system/plugin.py` | `Plugin` ABC, `PluginState` enum |
| `src/core/plugin_system/decorators.py` | `@plugin(name=..., version=...)` |
| `src/core/plugin_system/registry.py` | `PluginRegistry` — staged discovery (`tier=bootstrap|deferred|all`) |
| `src/core/plugin_system/discovery_scan.py` | Filesystem + AST scan for `@plugin(startup_tier=...)` and tab `startup_tier`, plus the build-time manifest loader |
| `src/core/plugin_system/discovery_manifest.json` | Generated entry-point list for frozen builds (see [Discovery manifest](#discovery-manifest-frozen-builds)) |
| `src/devtools/gen_discovery_manifest.py` | Writes / `--check`s the manifest from the tree |
| `src/core/plugin_system/lifecycle.py` | `PluginLifecycleManager` — initialize / activate / deactivate / shutdown loop (log-only error path; emits no events) |
| `src/core/plugin_system/interfaces.py` | `IControllablePlugin`, `IServicePlugin`, `ISessionPlugin` |
| `src/core/plugin_system/settings.py` | `PluginSettings` / `SettingsScope` / `auto_persist` — a per-plugin `QSettings` group helper; exported from `core.plugin_system` but **no app plugin uses it** today (settings persistence is centralized, see [SETTINGS_PERSISTENCE.md](SETTINGS_PERSISTENCE.md)) |
| `src/core/plugin_coordinator.py` | `PluginCoordinator` — event bus + lifecycle + session blueprints |
| `src/core/bootstrap.py:_initialize_plugins` | The single wiring site |

The old capability/manifest layer (`contributions.py` / `PluginDefinitionRegistry`)
is gone — the module no longer exists and nothing in `src/` references it.
Discovery is the registry scan below; plugin *declarations* still live in code
(`@plugin`), never in a hand-maintained list. The one generated file,
`discovery_manifest.json`, is derived data for frozen builds — see
[Discovery manifest](#discovery-manifest-frozen-builds).

## Bootstrap flow (`src/core/bootstrap.py`)

**Bootstrap tier** (before main window is usable):

```
discover_plugins(tier="bootstrap")                 # registry scan + import + instantiate
  └─► PluginCoordinator.register_plugins           # lifecycle.register + session blueprints
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

## Discovery

`PluginRegistry` (`src/core/plugin_system/registry.py`) exposes
`discover_plugins(*, tier="bootstrap"|"deferred"|"all")`:

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

## Discovery manifest (frozen builds)

Discovery reads `src/core/plugin_system/discovery_manifest.json` **first**. It
is a generated list of entry points — `{"kind": "tab"|"plugin", "id", "module",
"attr", "startup_tier", "startup_order"}`, sorted by `(kind, id)` — so a frozen
PyInstaller bundle, which ships no `.py` files on disk, discovers tabs and
plugins without importing a single module just to find them. Nothing in the
file is hand-written: it is derived from the tree by AST.

```bash
PYTHONPATH=src python3 src/devtools/gen_discovery_manifest.py          # write
PYTHONPATH=src python3 src/devtools/gen_discovery_manifest.py --check  # verify, exit 1 on drift
```

Regenerate after adding, removing or renaming a tab package, a `plugin.py`, or a
`@plugin(...)` entry point. `tests/runtime/test_discovery_manifest.py` pins the
committed file to the tree (freshness), pins discovery-with-manifest to zero
tab/plugin imports, and pins fail-open; a stale manifest fails the suite instead
of shipping.

Order of authority in `discovery_scan.iter_tab_entry_points()` /
`iter_plugin_entry_points()`:

1. the manifest, when it exists and parses — **no** module is imported to discover;
2. otherwise the filesystem AST scan (dev checkouts);
3. otherwise `pkgutil` + import (frozen bundle with no manifest).

Inside step 3, a package under `src/tabs/` that ships no `tab.py` (e.g.
`use_cases`) is a candidate, not a broken tab: the scan asks
`importlib.util.find_spec` before importing and skips a non-resolving module
quietly (DEBUG; a raising `find_spec` — broken parent, relative name — counts
as "not resolvable"). Only a module that exists but fails to import is an
ERROR with a traceback, so a genuinely broken `tab.py` still shows up in the
frozen startup log.

The manifest is consulted only for the real tree (`src_root=None`); an explicit
`src_root` (tests, fixture trees) always runs the filesystem/import scan.
Anything wrong with the file — missing, unreadable, corrupt JSON, unknown
`version`, a malformed record — fails **open**: one warning from
`discovery_scan`, `load_discovery_manifest()` returns `None`, and the import
scan runs unchanged. A bad manifest never crashes startup.

Frozen builds must run the write form before PyInstaller collects data and ship
`discovery_manifest.json` next to `discovery_scan.py` in the bundle
(it is resolved with `Path(__file__).with_name(...)`). The build templates are
**not** wired to this yet: the Windows spec's `APP_DATAS` and the Linux/Flatpak
equivalents still need both the generator call and the data entry.

## The `Plugin` contract (`src/core/plugin_system/plugin.py:17`)

```python
class Plugin(ABC):
    context: Any | None
    _state: PluginState                              # private; read by the lifecycle manager
    @abstractmethod
    def initialize(self, context: Any) -> None         # MUST call super().initialize(context)
    def activate(self) -> None
    def deactivate(self) -> None
    def shutdown(self) -> None
    def _set_state(self, state: PluginState) -> None
```

`PluginState`: `CREATED → INITIALIZED → ACTIVE → INACTIVE → SHUTDOWN`, plus `ERROR` (set by lifecycle manager on exception).

There is **no** `get_ui_components` / `get_toolbar_actions` / `get_menu_items` /
`get_render_entities` / `get_definition` / `plugin_resource_path` / `get_state`.
A plugin contributes behaviour by implementing the interfaces below (or its own
tab contract / services) and by owning its normal package code; UI chrome is
contributed through the tab/action catalogues, not through `Plugin` hooks.

### Optional interfaces (`src/core/plugin_system/interfaces.py`)

- **`IControllablePlugin`** — `get_controller()` + `handle_command(command, ...)`. Lets `PluginCoordinator.execute_command(plugin_name, command, ...)` dispatch without knowing the method name.
- **`IServicePlugin`** — `get_service()`.
- **`ISessionPlugin`** — `get_session_blueprints() -> tuple[SessionBlueprint, ...]`. The coordinator registers these; the workspace creates sessions via `create_session(store, session_type)`.

## Inventory

Live `@plugin` entry points (2026-10-22). Source of truth: filesystem scan of every `plugin.py` under `src/plugins/` and `src/tabs/` (incl. nested `tabs/*/plugins/*/`).

Per-plugin docs: app-wide plugins → [plugins/](plugins/index.md); tab-owned plugins → `src/tabs/<tab>/docs/plugins/`.

### App-wide (`src/plugins/`)

| Name | Path | Tier | Order | Interfaces | Role | Doc |
|---|---|:-:|---|---|---|
| `diagnostics` | `plugins/diagnostics/` | bootstrap | — | `IControllablePlugin`, `IServicePlugin` | Local-first crash/diagnostics report (env + logs + breadcrumbs, redacted); "Report a problem" dialog with Copy / Save / Open issue. No auto-upload, no screenshots | — |
| `settings` | `plugins/settings/` | bootstrap | — | `IServicePlugin` | Settings dialog, `SettingsManager` disk persistence, canvas-feature setting bindings | [plugins/settings.md](plugins/settings.md) |
| `layout` | `plugins/layout/` | bootstrap | — | — | UI-mode subscriber; obtains `layout_manager` via tab `create_startup_service` (not a local manager module) | [plugins/layout.md](plugins/layout.md) |
| `onboarding` | `plugins/onboarding/` | bootstrap | — | — | First-run UI-mode picker on the startup stack; reads `SettingsManager.is_first_run` | [plugins/onboarding.md](plugins/onboarding.md) |
| `export` | `plugins/export/` | deferred | 10 | `IControllablePlugin`, `IServicePlugin` | Still/video export dialog, recording/clipboard commands, export QSS | [plugins/export.md](plugins/export.md) |
| `help` | `plugins/help/` | deferred | — | `IControllablePlugin` | In-app help dialog (hub/tree); see [HELP_SYSTEM.md](HELP_SYSTEM.md) | [plugins/help.md](plugins/help.md) |
| `image_properties` | `plugins/image_properties/` | deferred | — | `IControllablePlugin` | Image metadata dialog + `service.build_image_properties` | [plugins/image_properties.md](plugins/image_properties.md) |

### Tab / session plugins (`src/tabs/`)

| Name | Path | Tier | Order | Interfaces | Role | Doc |
|---|---|:-:|---|---|---|
| `comparison` | `tabs/image_compare/` | bootstrap | — | `ISessionPlugin` | Primary two-image compare tab; owns analysis services (`services/analysis/`), session controller, canvas | `tabs/image_compare/docs/plugins/comparison.md` |
| `session_picker` | `tabs/session_picker/` | bootstrap | — | `ISessionPlugin` | Transient "New Tab" session browser / switcher | `tabs/session_picker/docs/plugins/session_picker.md` |
| `multi_compare` | `tabs/multi_compare/` | deferred | — | `ISessionPlugin` | Grid multi-image compare tab + `multi_compare.state` slot | `tabs/multi_compare/docs/plugins/multi_compare.md` |
| `image_gallery` | `tabs/image_gallery/` | deferred | — | `ISessionPlugin` | Media gallery tab; owns the `gallery` session slot (`GALLERY_SLOT_NAME`) with its own batch analysis pipeline | `tabs/image_gallery/docs/plugins/image_gallery.md` |
| `video_editor` | `tabs/image_compare/plugins/video_editor/` | deferred | 0 | `ISessionPlugin` | Tab-owned video editor (dialogs, timeline, recorder/export flows); loads before `export` | `tabs/image_compare/docs/plugins/video_editor.md` |

There is no `@plugin(name="analysis")` and no opaque analysis state on the
viewport. Diff/metrics/SSIM live under `tabs/image_compare/services/analysis/`
and `shared/analysis/`, constructed by `ComparisonPlugin`; their values are
Store state (`SET_DIFF_MODE` / `SET_PSNR_VALUE` / `SET_SSIM_VALUE`) — see
[STORE.md](STORE.md).

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
├── events/                # AnalysisSetChannelViewModeEvent, AnalysisSetDiffModeEvent
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
- **`events.py`** declares the plugin's outbound events for EventBus when the plugin publishes cross-component facts.

## Lifecycle invariants

1. **Construct lazily in `initialize`**, not `__init__`. Services need `context.store`, `event_bus`, etc., which only exist at initialize time.
2. **Always call `super().initialize(context)`.** Without it `self.context` is `None` and state stays `CREATED`.
3. **Don't reach into other plugins' internals.** Use `EventBus` for cross-plugin signals; use `PluginCoordinator.execute_command(plugin_name, command, ...)` if you really need a method call. Direct imports between plugins are a smell.
4. **Errors during `_safe_call` are logged and set `PluginState.ERROR`** — the lifecycle manager emits no event and does not propagate the exception (`lifecycle.py:92-97`). Watch the log; there is no subscribe-able failure signal.
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
4. (Optional) If your plugin defines a workspace session type, implement `ISessionPlugin.get_session_blueprints()`.
5. **Nothing else** — discovery is automatic; declare `startup_tier` on `@plugin`. Re-run `src/devtools/gen_discovery_manifest.py` so the committed manifest (and its freshness test) matches.

## See also

- [STORE.md](STORE.md) — how plugins read/write app state
- [EVENT_BUS.md](EVENT_BUS.md) — cross-plugin async comms
- [rendering/index.md](rendering/index.md) — the orthogonal plugin system for canvas-tools
- [tabs/index.md](tabs/index.md) — workspace tab/session interface
