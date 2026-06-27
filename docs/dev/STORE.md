# Store / Redux

Single source of truth for application state. All state mutations go through one path:

```
Action  ──►  Dispatcher.dispatch  ──►  RootReducer.reduce  ──►  new Store  ──►  emit_state_change(scope)
```

This document is the contract reference. For the broader "why" and architectural intent, see [CONTRACTS.md](CONTRACTS.md).

## Files at a glance

| Path | Role |
|---|---|
| `src/core/store.py` | `Store` — root holder of `viewport`, `document`, `settings`, `workspace`, `runtime_cache` |
| `src/core/store_viewport.py` | Dataclasses: `ViewportState`, `ViewState`, `InteractionState`, `GeometryState`; legacy compatibility imports for image render/session data while migration C9 is in progress |
| `src/tabs/image_compare/state/models.py` | Image-compare render/session/cache models (`RenderConfig`, `ImageSessionState`, `RenderCacheState`, `SessionData`) |
| `src/core/store_document.py` | `DocumentModel`, `ImageItem` |
| `src/core/store_settings.py` | `SettingsState`, `WorkerStoreSnapshot` |
| `src/core/store_workspace.py` | `WorkspaceStoreMixin` (sessions/tabs) |
| `src/core/store_operations.py` | `StoreOperationsMixin` (helpers around state) |
| `src/core/state_management/action_base.py` | `Action` ABC + `ActionType` enum |
| `src/core/state_management/*_actions.py` | Concrete action dataclasses, grouped by domain |
| `src/core/state_management/reducers.py` | `RootReducer` + generic per-substate reducers |
| `src/core/state_management/extension_reducers.py` | Registry for tab-owned reducers contributed through `TabContract.contribute_reducers(...)` |
| `src/core/state_management/dispatcher.py` | `Dispatcher` — the only mutation gate |
| `src/ui/store_bridge.py` | `QtStoreBridge` — wraps `store.on_change()` into Qt `Signal(str)` |
| `src/core/tracing/instrumentation.py` | Optional tracing wrapper around `emit_state_change` |

## Core API

### Store (`src/core/store.py:39`)

```python
class Store(WorkspaceStoreMixin, StoreOperationsMixin):
    viewport: ViewportState
    document: DocumentModel
    settings: SettingsState
    workspace: WorkspaceState
    runtime_cache: ViewportRuntimeCache
    state_changed: Signal(str)  # injected by QtStoreBridge

    def on_change(cb: Callable[[str], None]) -> None
    def emit_state_change(scope: str = "viewport") -> None
    def emit_viewport_change(subdomain: str | None = None) -> None  # scope = "viewport" or f"viewport.{subdomain}"
    def get_dispatcher() -> Dispatcher
```

### Dispatcher (`src/core/state_management/dispatcher.py:29`)

```python
dispatcher.dispatch(action: Action, scope: str = "viewport") -> None
dispatcher.subscribe(cb: Callable[[Action], None]) -> None    # action listener (post-dispatch)
dispatcher.get_action_history() -> list[Action]               # last 100 actions
```

`dispatch` is thread-safe (`threading.Lock`). It calls `RootReducer.reduce`, swaps `store.viewport`/`document`/`settings` references **on the same Store instance**, re-points the active workspace session to the new sub-states, preserves opaque plugin states (`_viewport_plugin_state`, `_analysis_plugin_state`), then emits `emit_state_change(scope)`.

### Action (`src/core/state_management/action_base.py:94`)

```python
@dataclass
class Action(ABC):
    type: str                          # ActionType enum value
    def get_payload(self) -> dict[str, Any]
```

`ActionType` is the canonical enum of all action keys. Each concrete action is a dataclass in one of the `*_actions.py` files (viewport, interaction, geometry, session, document, settings, appearance, cache).

### Reducers (`src/core/state_management/reducers.py`)

Per-domain stateless classes, all returning a **new** dataclass via `dataclasses.replace`:

| Reducer | Line | Reduces |
|---|---|---|
| `ViewStateReducer` | 106 | `ViewState` |
| `InteractionStateReducer` | 137 | `InteractionState` |
| `GeometryStateReducer` | 172 | `GeometryState` |
| `RenderConfigReducer` | delegates | `RenderConfig` plus tab-owned extension reducers |
| `ViewportReducer` | delegates | `ViewportState` plus tab-owned session-data reducers |
| `DocumentReducer` | delegates | `DocumentModel` |
| `SettingsReducer` | delegates | `SettingsState` |
| `RootReducer` | delegates | `Store` (composes viewport + document + settings) |

Image-compare reducers live in `src/tabs/image_compare/state/reducers.py` and
are registered by `ImageCompareTab.contribute_reducers(...)`; core reducers do
not import that module directly.

## Scopes (the `emit_state_change` argument)

Subscribers filter on the `scope` string. Conventions:

- `"viewport"` — broadest viewport change; subscribers that don't care about subdomain.
- `"viewport.<subdomain>"` — narrower; e.g. `"viewport.geometry"`, `"viewport.interaction"`, `"viewport.session_data"`.
- `"document"` — image list / current index changes.
- `"settings"` — preferences / theme / language.
- `"workspace"` — session add/remove/switch.

Filter pattern in a subscriber:

```python
def _on_store_changed(self, scope: str) -> None:
    if scope == "settings" or scope == "viewport" or scope.startswith("viewport."):
        self.refresh()
```

## Subscribing

There are **two** subscription mechanisms — pick by use case:

### 1. Qt signal — for UI
`QtStoreBridge` (`src/ui/store_bridge.py`) installs `store.state_changed = Signal(str)`. UI widgets connect like any Qt signal:

```python
self.store.state_changed.connect(self._on_store_changed)
# remember to disconnect on teardown
self.store.state_changed.disconnect(self._on_store_changed)
```

### 2. Plain callback — for non-Qt code
`Store.on_change(cb)` adds a `Callable[[str], None]`. No removal API — use only for app-lifetime listeners (e.g. recorder, instrumentation).

## Invariants — what you MUST hold

1. **Never mutate state in-place.** Reducers must return new dataclasses (`dataclasses.replace(state, field=value)`), not `state.field = value`. Same rule for UI/services: dispatch an action, never write `store.viewport.X = Y` directly. (Common offender — see `src/ui/canvas_presentation/plan_builder.py` for in-progress migration.)
2. **All state changes go through the Dispatcher.** Direct mutation skips:
   - the lock (race conditions),
   - action history (tracing/devtools),
   - dispatcher subscribers,
   - the `emit_state_change` call (subscribers won't know).
3. **Feature commands must emit a viewport change.** When a feature mutates feature-state outside the Action/Reducer path (e.g. via `Store.update_canvas_feature_state`), it must call `store.emit_viewport_change()`. Guard with `hasattr(store, 'emit_viewport_change')` because `StoreProxy` (used during init) doesn't expose it yet:
   ```python
   if hasattr(store, "emit_viewport_change"):
       store.emit_viewport_change("interaction")
   ```
4. **No back-loops.** A subscriber must not dispatch an action whose reducer triggers the same scope synchronously. There is no built-in re-entry guard at the dispatcher level (the lock would deadlock). Use a flag, or defer with `QTimer.singleShot(0, ...)`.
5. **Workspace sessions own their substate.** When you dispatch, `Dispatcher` re-points the active session's `document`/`viewport` to the new instances. If you bypass dispatch and assign a new instance manually, the session keeps the old reference → switching sessions restores stale state.

## Extension recipe — adding a new action

1. **Add the enum value** in `src/core/state_management/action_base.py:ActionType`.
2. **Add the action dataclass** in the appropriate `*_actions.py` (e.g. `interaction_actions.py`):
   ```python
   @dataclass
   class SetFooMode(Action):
       enabled: bool
       type: str = ActionType.SET_FOO_MODE.value
       def get_payload(self): return {"enabled": self.enabled}
   ```
3. **Add a branch in the matching reducer** (`reducers.py`):
   ```python
   if action.type == ActionType.SET_FOO_MODE.value:
       return replace(state, foo_mode=action.enabled)
   ```
4. **Dispatch from caller** (UI/presenter/service):
   ```python
   store.get_dispatcher().dispatch(SetFooMode(True), scope="viewport.interaction")
   ```
5. **Subscriber** filters on `scope.startswith("viewport.interaction")` (or `"viewport"`).

## Plugin state — the escape hatch

Plugins (analysis, export) keep state outside the Action/Reducer path via opaque attributes on `viewport`:
- `viewport._viewport_plugin_state` — viewport-level
- `viewport._analysis_plugin_state` — view-state level

`Dispatcher` preserves these across reductions and re-syncs matching fields back into the new viewport via `_sync_plugin_states`. Don't add new opaque attrs without updating the dispatcher.

## See also

- [CONTRACTS.md](CONTRACTS.md) — architectural principles behind the Store pattern
- [EVENT_BUS.md](EVENT_BUS.md) — async/decoupled comms (use this, not Store, for cross-plugin events)
- [TRACING.md](TRACING.md) — wrapping `emit_state_change` for diagnostics
