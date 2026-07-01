# EventBus

Decoupled, type-safe pub/sub for cross-component async notifications. Use it when one part of the app needs to tell another that *something happened*, but neither should know about the other.

`EventBus` is **not** for state — state lives in the [Store](STORE.md). EventBus events are facts about the past ("an export finished"), not state changes.

## Files

| Path | Role |
|---|---|
| `src/core/plugin_system/event_bus.py` | `EventBus` class, `MAX_EMIT_DEPTH`, `EventBusDepthExceeded` |
| `src/core/events.py` | Cross-cutting domain events (frozen dataclasses) |
| `src/plugins/<x>/events.py` | Plugin-local events (e.g. `ComparisonUpdateRequestedEvent`) |

Single instance is held by `ApplicationContext.event_bus` (`src/core/bootstrap.py`) and passed into plugins via `Plugin.initialize(context)`.

## API (`src/core/plugin_system/event_bus.py:32`)

```python
class EventBus:
    def subscribe(event_type: Type[T], callback: Callable[[T], None]) -> None
    def unsubscribe(event_type: Type[T], callback: Callable[[T], None]) -> None
    def emit(event: Event) -> None
```

- `event_type` is a class; routing is **by exact type** (no subclass matching).
- Callbacks are stored as weak references where possible:
  - bound method → `weakref.WeakMethod`
  - module-level function → `weakref.ref`
  - lambda or closure → `_StrongRefWrapper` (strong; you must `unsubscribe` to release)
- Dead weak refs are pruned lazily during `emit`.
- Duplicate subscription of the same `callback` is silently skipped.

## Defining an event (`src/core/events.py`)

Frozen dataclass, no behavior:

```python
@dataclass(frozen=True)
class ExportFinishedEvent:
    path: str
    success: bool
```

Place it where it makes sense to import:
- Cross-plugin / cross-layer: `src/core/events.py`
- Plugin-local (only this plugin emits and consumes): `src/plugins/<x>/events.py`

## Depth limit (re-entrancy guard)

`MAX_EMIT_DEPTH = 10` (`event_bus.py:15`). A thread-local emit chain is tracked; if a subscriber re-emits and the chain reaches 10, `EventBusDepthExceeded` is raised with the chain in the message.

This is **not** a back-pressure mechanism — it's a tripwire for accidental cycles. If you hit it, you've designed a loop. Fix the design (defer the emit with `QTimer.singleShot(0, ...)`, or restructure so the subscriber doesn't trigger the same event chain).

## Error isolation

A callback exception is logged (`logger.error(..., exc_info=True)`) but does **not** stop other subscribers from receiving the event. The only exception that propagates is `EventBusDepthExceeded` — by design, so the cycle surfaces.

## Thread safety

`emit` is safe to call from any thread (each thread has its own depth chain via `threading.local()`). Subscribers are invoked on the calling thread — if a subscriber touches Qt widgets, marshal to the UI thread yourself (`QMetaObject.invokeMethod` / `QTimer.singleShot(0, ...)`).

## When to use EventBus vs Store

| Need | Use |
|---|---|
| "X just happened" notification | **EventBus** |
| Read current state | **Store** |
| Mutate state | **Store** (via Dispatcher) |
| One component needs to know about another's UI action | **EventBus** (publisher-side) |
| Multiple subscribers need to react to the same state change | **Store** (`state_changed` signal with scope) |

Rule of thumb: if the receiver only needs to do something *once* per occurrence, EventBus. If the receiver needs to re-render based on current state, Store.

## Extension recipe

1. **Define the event** (frozen dataclass) in `core/events.py` or `plugins/<x>/events.py`.
2. **Subscribe** from the receiver, typically in `Plugin.initialize(context)`:
   ```python
   def initialize(self, context):
       super().initialize(context)
       context.event_bus.subscribe(ExportFinishedEvent, self._on_export_finished)
   ```
   Prefer a bound method (weak ref). A lambda will be held strongly — fine for app-lifetime, leaks for short-lived subscribers.
3. **Emit** from the publisher:
   ```python
   self.context.event_bus.emit(ExportFinishedEvent(path=p, success=True))
   ```
4. **Unsubscribe** in `Plugin.shutdown()` if the subscriber outlives the bus (rare).

## Built-in events (selected)

- `core/events.py:PluginEvent(plugin_name, stage)` — emitted by `PluginLifecycleManager` on initialize/activate/deactivate/shutdown/error.
- `tabs/image_compare/events.py:ComparisonUpdateRequestedEvent` — comparison tab asks for a recomputation.
- `tabs/image_compare/events.py:ComparisonErrorEvent` — comparison failure.
- `tabs/image_compare/events.py:Analysis*` — analysis / metrics signals.

See `src/plugins/*/events.py` for the full set.

## See also

- [PLUGINS.md](PLUGINS.md) — how plugins receive the bus via `initialize(context)`
- [STORE.md](STORE.md) — the alternative path for state-driven notifications
