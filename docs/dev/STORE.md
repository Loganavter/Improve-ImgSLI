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
| `src/core/store_viewport.py` | Dataclasses: `ViewportState`, `ViewState`, `InteractionState`, `GeometryState`, plus the cross-tab `RenderConfig` / `SessionData` containers |
| `src/tabs/image_compare/state/models.py` | Tab-owned cache/session models (`ImageSessionState`, `RenderCacheState`, `PipelineCacheState`) |
| `src/tabs/image_compare/state/document.py` | `DocumentModel`, `ImageItem` — value of the tab's `document` session slot (tab-owned, not core) |
| `src/core/store_settings.py` | `SettingsState`, `WorkerStoreSnapshot` |
| `src/core/store_workspace.py` | `WorkspaceStoreMixin` (sessions/tabs) |
| `src/core/store_operations.py` | `StoreOperationsMixin` (helpers around state) |
| `src/core/state_management/action_base.py` | `Action` ABC + `ActionType` enum |
| `src/core/state_management/*_actions.py` | Concrete action dataclasses, grouped by domain |
| `src/core/state_management/reducers.py` | `RootReducer` + generic per-substate reducers |
| `src/core/state_management/extension_reducers.py` | Registry for tab-owned session-data (`register_session_data_reducer`) and render-config (`register_render_config_reducer`) reducers |
| `src/core/state_management/slot_reducers.py` | `register_state_slot_reducer` — registry of tab-owned session-slot reducers that `RootReducer` runs generically |
| `src/core/state_management/transaction.py` | `TransactionAction` — the batch action dispatched by `Store.transact` |
| `src/core/state_management/viewport_scopes.py` | `LIGHTWEIGHT_VIEWPORT_SUBDOMAINS` — the `viewport.<sub>` scopes that skip the full chrome batch |
| `src/core/state_management/dispatcher.py` | `Dispatcher` — the only mutation gate |
| `src/ui/store_bridge.py` | `QtStoreBridge` — wraps `store.on_change()` into Qt `Signal(str)` |
| `src/core/tracing/instrumentation.py` | Optional tracing wrapper around `emit_state_change` |

## Core API

### Store (`src/core/store.py:34`)

```python
class Store(WorkspaceStoreMixin, StoreOperationsMixin):
    viewport: ViewportState        # @property over the active session
    document: DocumentModel        # @property over the active session
    settings: SettingsState
    workspace: WorkspaceState
    runtime_cache: ViewportRuntimeCache
    state_changed: Signal(str)  # injected by QtStoreBridge

    def on_change(cb: Callable[[str], None]) -> None
    def emit_state_change(scope: str = "viewport") -> None
    def emit_viewport_change(subdomain: str | None = None) -> None  # scope = "viewport" or f"viewport.{subdomain}"
    def batch_changes() -> ContextManager[None]  # defer emissions; flush once at exit
    def get_dispatcher() -> Dispatcher
```

`batch_changes()` defers every `emit_state_change` inside the block and flushes
each scope once (first-emitted order) when the block exits. Reads inside the
block see the mutated store immediately — only notifications are deferred. Use
it when several store mutations are one user-visible transition whose
intermediate states must never reach subscribers (e.g. the session-picker
replace: `create_workspace_session` + `close_workspace_session` must not paint
a two-tab strip in between). Backed by `Store.replace_workspace_session` /
`WorkspaceSessionActions.replace_workspace_session`.

`store.document` / `store.viewport` are **properties** over the active workspace
session's substate (`store.py:63-91`), not fields on `Store`; before the first
session exists they fall back to `_pre_session_document` /
`_pre_session_viewport`.

### Batching — Transaction (Phase 5)

`Store.transact(actions, scope="document")` coalesces N actions into one
`Dispatcher.dispatch(TransactionAction)` → one `RootReducer.reduce` → one
`emit_state_change(scope)`. For image browsing this collapses 6–10 dispatches
(`SetFullResImage` + `SetPreviewImage` + `SetImagePath` + `SetImageSessionImage` …)
to 1 dispatch / 1 `ViewportState` alloc (verified `IMGSLI_TRACE=1` `dispatch.begin/end`
exactly 1 per `set_current_image`). The reducer chains inner actions without
intermediate `Store` allocs. `Dispatcher` is reentrant-safe (reduce runs
**outside** `_lock`, which is taken only for the `is`-comparison + reference
swap at `dispatcher.py:333`; subscriber snapshot and `emit_state_change`
follow outside the lock at `dispatcher.py:447-462`), so `on_change → dispatch`
needs no `QTimer`. Legacy `batch_changes` remains for `persistence.py` but
nested scopes dedup (already).

For LOD, `PyramidBuildCoordinator` publishes `store.publish("lod_available")`
per level with `await idle` between levels instead of `invalidate_render` per
level — the canvas LOD selector consumes new levels without a full
pick-signature invalidation; only the final flip calls
`invalidate_render_state`.

### Dispatcher (`src/core/state_management/dispatcher.py:175`)

```python
dispatcher.dispatch(action, scope: str = "viewport", session_id: str | None = None) -> None
dispatcher.subscribe(cb: Callable[[Action], None]) -> None       # action listener (post-dispatch)
dispatcher.unsubscribe(cb: Callable[[Action], None]) -> None
dispatcher.get_action_history() -> list[Action]                 # last 100 actions
dispatcher.clear_history() -> None
dispatcher.bind_history_for_session(session_id: str) -> None    # point undo/history at a session's slots
dispatcher.undo() / dispatcher.redo() -> None                   # per-session reference-snapshot undo/redo
dispatcher.can_undo() / dispatcher.can_redo() -> bool
```

`session_id` (Wave CORE session targeting) defaults to `None` = active-session
behaviour. An explicit id addresses that session's slots for
snapshot → reduce → write-back and binds the dispatch's history bookkeeping to
that session, without touching the dispatcher's standing binding; viewport and
settings stay active-scoped in both paths. `Store.transact(…, session_id=…)`
threads it through.

Undo/redo: `dispatch` stores `(type, before, after)` reference-snapshots of the
active session's `viewport` + every slot-reducer slot for the
`Dispatcher._UNDOABLE_TYPES` action allowlist (see
[tabs/session-lifecycle.md](tabs/session-lifecycle.md));
continuous gestures coalesce; redo clears on the next dispatch; both no-op
while an image is loading. Covers image_compare and multi_compare session
state alike (both are slot-reducer slots).

`dispatch` is thread-safe (`threading.Lock`). It calls `RootReducer.reduce`, swaps `store.viewport`/`settings` references and **every registered slot-reducer slot** (`document`, `pipeline`, `multi_compare.state`, `gallery`) **on the same Store instance**, then re-points the active workspace session to the new sub-states and emits `emit_state_change(scope)`.

### Action (`src/core/state_management/action_base.py:110`)

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
| `ViewStateReducer` | 98 | `ViewState` (including `canvas_widget_state`, via each feature's `reduce_view_state`) |
| `InteractionStateReducer` | 172 | `InteractionState` |
| `GeometryStateReducer` | 233 | `GeometryState` |
| `ViewportReducer` | 308 | `ViewportState` — composes the three above plus the registered session-data reducers |
| `SettingsReducer` | 345 | `SettingsState` |
| `RootReducer` | 435 | `Store` (composes viewport + settings + every registered slot reducer) |

There is no core `RenderConfigReducer`: `RootReducer._reduce_one` applies
`reduce_render_config_extensions` to the viewport's config after
`ViewportReducer` runs, and the registered tab reducer does the work.

Tab-owned reducers (each registered by the tab, never imported by core):

| Reducer | Path | Reduces |
|---|---|---|
| `DocumentReducer` | `src/tabs/image_compare/state/reducer.py:21` | `DocumentModel` — slot `document` |
| `PipelineCacheReducer` | `src/tabs/image_compare/state/reducers.py:141` | `PipelineCacheState` — slot `pipeline` |
| `SessionDataReducer` | `src/tabs/image_compare/state/reducers.py:105` | `SessionData` — session type `image_compare` (composes `ImageSessionReducer:57` + `RenderCacheReducer:77`) |
| `ImageRenderConfigReducer` | `src/tabs/image_compare/state/reducers.py:477` | `RenderConfig` |

**Registration.** `TabContract` has no reducer hook. Registration is an import
side effect of the tab's `plugin.py`: `src/tabs/image_compare/plugin.py:5` does
`import tabs.image_compare.bootstrap_reducers  # noqa: F401`, and
`src/tabs/image_compare/bootstrap_reducers.py:16-19` calls
`register_state_slot_reducer("document" | "pipeline", …)`,
`register_session_data_reducer("image_compare", …)` and
`register_render_config_reducer(ImageRenderConfigReducer.reduce)`.
`RootReducer` then runs the slot reducers generically via
`iter_state_slot_reducers()` without importing the tab module.
`multi_compare` and `image_gallery` follow the same shape
(`register_multi_compare_reducers`, `register_gallery_reducers`).

## Scopes (the `emit_state_change` argument)

Subscribers filter on the `scope` string. Conventions:

- `"viewport"` — broadest viewport change; subscribers that don't care about subdomain.
- `"viewport.<subdomain>"` — narrower. The sanctioned lightweight subdomains are exactly `"viewport.interaction"`, `"viewport.geometry"`, `"viewport.overlay"` (`LIGHTWEIGHT_VIEWPORT_SUBDOMAINS` in `src/core/state_management/viewport_scopes.py:29`) — both chrome handlers skip them and the owning feature repaints directly. Emit any other subdomain and you pay for the full chrome batch anyway.
- `"document"` — image list / current index changes.
- `"settings"` — preferences / theme / language.
- `"workspace"` — session add/remove/switch.

LOD readiness is not an `emit_state_change` scope: `PyramidBuildCoordinator`
publishes it with `store.publish("lod_available")`
(`src/engine/pyramid/coordinator.py:444`).

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

1. **Never mutate state in-place.** Reducers must return new dataclasses (`dataclasses.replace(state, field=value)`), not `state.field = value`. Same rule for UI/services: dispatch an action, never write `store.viewport.X = Y` directly.
2. **All state changes go through the Dispatcher.** Direct mutation skips:
   - the lock (race conditions),
   - action history (tracing/devtools),
   - dispatcher subscribers,
   - the `emit_state_change` call (subscribers won't know).
3. **Canvas feature state is an action, not a `Store` method.** A feature that
   keeps state in `view_state.canvas_widget_state[<feature>]` dispatches
   `SetCanvasWidgetStateAction(feature=…, state=…)` (real call site:
   `src/tabs/image_compare/canvas/features/magnifier/persistence.py:199`);
   `ViewStateReducer` copies the dict and stores the new state
   (`reducers.py:98-114`). `ActionType.SET_CANVAS_WIDGET_STATE` /
   `UPDATE_CANVAS_FEATURE_STATE` are handled there — `Store` has no
   `update_canvas_feature_state`. For a continuous, purely-visual update the
   owning feature repaints itself and emits a lightweight subdomain so the
   chrome batch is skipped:
   ```python
   store.emit_viewport_change("interaction")   # or "geometry" / "overlay"
   ```
4. **No back-loops.** `Dispatcher.dispatch` is reentrant-safe (reduce runs
   outside `_lock`, the lock is taken only for the `is`-comparison + reference
   swap at `dispatcher.py:333`, subscriber snapshot + `emit_state_change`
   follow outside it), so `store.on_change → dispatch` may run synchronously.
   `QTimer.singleShot(0, dispatch)` is now optional, not required. For
   multi-action user-visible transitions, prefer `store.transact([...], scope)`
   over `batch_changes` to get 1 alloc / 1 emit (see §Batching).
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

## Plugin state — removed (commit `b981d692`, 2026-07-11)

The old escape hatch — opaque `viewport._viewport_plugin_state` /
`viewport._analysis_plugin_state` attributes, preserved across reductions by a
`Dispatcher._sync_plugin_states` pass — no longer exists. `ViewportState` is a
`__slots__` dataclass holding only `render_config`, `session_data`,
`view_state`, `interaction_state`, `geometry_state`
(`src/core/store_viewport.py:263`), and the dispatcher swaps slot values
generically. A plugin or tab that needs per-session state registers a session
state slot (see [STATE_SLOT_MANIFEST.md](STATE_SLOT_MANIFEST.md)) and, if it
must reduce in-slot, a slot reducer (`register_state_slot_reducer`). Do not
reintroduce attribute smuggling — `tests/contracts/test_viewport_state_slots.py`
fails on unknown `viewport.<attr>` assignments.

## See also

- [CONTRACTS.md](CONTRACTS.md) — architectural principles behind the Store pattern
- [EVENT_BUS.md](EVENT_BUS.md) — async/decoupled comms (use this, not Store, for cross-plugin events)
- [TRACING.md](TRACING.md) — wrapping `emit_state_change` for diagnostics