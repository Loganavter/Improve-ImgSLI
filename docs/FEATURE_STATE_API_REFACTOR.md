# Feature State API Refactor — Complete Contract Decoupling

**Goal**: Remove viewport plugin as a central orchestrator. Each feature manages its own state directly via clean API.

**Status**: PLANNING → IMPLEMENTATION → VERIFICATION → CLEANUP

---

## Current Architecture (LEGACY)

```
viewport.magnifier_service
  → _execute_magnifier_command("overlay.set_internal_split", val)
  → get_canvas_feature_command_by_alias("overlay.set_internal_split")
  → magnifier feature command
```

**Problems**:
- ViewportMagnifierService = mediator between viewport and magnifier
- State queries via `_query_magnifier()` using aliases
- Other plugins can't manage magnifier without viewport plugin
- Removing viewport breaks feature management

---

## New Architecture (CLEAN)

```
any_plugin or service
  → canvas_feature_state_api.execute_command("magnifier", "set_internal_split", val)
  → magnifier.commands.set_internal_split(store, val)
```

**Key changes**:
- Direct feature → feature communication
- No aliases, no intermediaries
- Features are independent and composable
- Viewport is just another plugin, not an orchestrator

---

## Implementation Plan

### Phase 1: Enrich Feature Contract

**File**: `src/ui/canvas_infra/scene/widget_contract.py`

1. Remove hardcoded defaults for `group_id`/`group_label`:
   ```python
   group_id: str | None = None
   group_label: str | None = None
   ```

2. Add state query/command builders to `CanvasWidgetFeature`:
   ```python
   @dataclass
   class CanvasFeatureStateQuery:
       query_id: str
       handler: Callable[..., Any]  # (store) -> dict or value

   @dataclass
   class CanvasFeatureStateCommand:
       command_id: str
       handler: Callable[..., None]  # (store, *args) -> None

   build_state_queries: BuildCanvasFeatureStateQueriesFn | None = None
   build_state_commands: BuildCanvasFeatureStateCommandsFn | None = None
   ```

### Phase 2: Create State API in Registry

**File**: `src/ui/canvas_infra/scene/feature_state_api.py` (NEW)

```python
def query_feature_state(feature_name: str, query_id: str, *args, **kwargs) -> Any:
    """Get feature state without aliases."""

def execute_feature_command(feature_name: str, command_id: str, *args, **kwargs) -> None:
    """Execute feature command directly."""

def has_feature_command(feature_name: str, command_id: str) -> bool:
    """Check if feature supports command."""
```

**In registry**:
- `get_canvas_feature_state_queries()` — registry of queries
- `get_canvas_feature_state_commands()` — registry of commands

### Phase 3: Migrate Magnifier Service

**File**: `src/plugins/viewport/magnifier_service.py` → DELETE

1. Move logic to feature itself OR inline in viewport plugin
2. Replace `_query_magnifier()` calls with `query_feature_state("magnifier", ...)`
3. Replace `_execute_magnifier_command()` calls with `execute_feature_command("magnifier", ...)`

Example migration:
```python
# OLD
_execute_magnifier_command(self.store, "overlay.set_internal_split", val)

# NEW
from ui.canvas_infra.scene.feature_state_api import execute_feature_command
execute_feature_command(self.store, "magnifier", "set_internal_split", val)
```

### Phase 4: Update Feature Manifests

Each feature's manifest registers queries/commands:

**Example** — `src/ui/canvas_features/magnifier/manifest.py`:
```python
def build_state_queries() -> tuple[CanvasFeatureStateQuery, ...]:
    return (
        CanvasFeatureStateQuery(
            query_id="active_state",
            handler=lambda store: {...}
        ),
        CanvasFeatureStateQuery(
            query_id="all_states",
            handler=lambda store: [...]
        ),
    )

def build_state_commands() -> tuple[CanvasFeatureStateCommand, ...]:
    return (
        CanvasFeatureStateCommand(
            command_id="set_internal_split",
            handler=lambda store, val: ...
        ),
    )
```

### Phase 5: Remove Aliases from Commands

**Transition**:
1. Keep old `command_aliases` for backward compatibility (with deprecation warning)
2. New code uses `feature_state_api.execute_feature_command()`
3. Remove alias-based discovery entirely

---

## Files to Modify

| File | Change | Phase |
|------|--------|-------|
| `widget_contract.py` | Add state query/command builders, remove viewport defaults | 1 |
| `widget_registry.py` | Add state API registration functions | 2 |
| `feature_state_api.py` | NEW — public API for queries/commands | 2 |
| `magnifier/manifest.py` | Register queries and commands | 4 |
| `divider/manifest.py` | Register queries and commands | 4 |
| `guides/manifest.py` | Register queries and commands | 4 |
| `capture/manifest.py` | Register queries and commands | 4 |
| `filename_overlay/manifest.py` | Register queries and commands | 4 |
| `viewport/magnifier_service.py` | DELETE | 3 |
| `viewport/plugin.py` | Refactor to use new API | 3 |

---

## Acceptance Criteria

- [ ] No `_query_magnifier()` or similar helper functions
- [ ] No `get_canvas_feature_command_by_alias()` in plugin code
- [ ] Features have explicit `build_state_queries()` and `build_state_commands()`
- [ ] viewport/magnifier_service.py deleted
- [ ] All tests pass (73 existing + new state API tests)
- [ ] Zero import of viewport in other plugins

---

## Benefits

✅ **Decoupling**: Viewport is optional, not critical
✅ **Composability**: Any plugin can query/command any feature
✅ **Testability**: Features tested in isolation
✅ **Clarity**: State API explicit in contract
✅ **Maintenance**: No hidden mediators or alias resolution
