# Capability aliases

Canvas features expose their behavior to shared (non-feature) code through **capability aliases** — string IDs like `"overlay.enabled"` or `"guides.set_thickness"`. Shared code looks up a callable by alias and invokes it; the feature can be renamed, moved, or replaced without rippling through callers.

This is the mechanism behind ImgSLI's "zero direct imports of features in shared code" rule.

## Files

| Path | Role |
|---|---|
| `src/ui/canvas_infra/scene/widget_contract.py` | `CanvasWidgetFeature`, `CanvasFeatureCommandAlias` dataclasses |
| `src/ui/canvas_infra/scene/widget_registry.py` | discovery, lookup, alias resolution |
| `src/tabs/image_compare/canvas/features/<name>/widget.py` (or `manifest.py`) | per-feature `WIDGET_FEATURE = CanvasWidgetFeature(...)` |

## The contract (`widget_contract.py`)

```python
@dataclass(frozen=True, slots=True)
class CanvasFeatureCommandAlias:
    capability_id: str   # public string callers use:   "overlay.enabled"
    command_id: str      # private id inside the feature: "query.enabled"

@dataclass(frozen=True, slots=True)
class CanvasWidgetFeature:
    name: str                                          # e.g. "magnifier"
    build_commands: Callable[[], dict[str, Handler]]   # {command_id: callable}
    command_aliases: tuple[CanvasFeatureCommandAlias, ...]
    # ... other contribution hooks (properties, gestures, toolbar bindings, ...)
```

Alias resolution is two-step:
1. `capability_id` → `(feature_name, command_id)` via the alias table
2. `(feature_name, command_id)` → callable via `build_commands()`

The split lets a feature reorganize internal commands without changing public IDs, and lets two features expose the same `command_id` name (e.g. both define `"query.enabled"`) without collision.

## Discovery

`get_canvas_widget_features()` (`widget_registry.py:48`) walks the feature packages registered via `register_canvas_widget_feature_package()` with `pkgutil`, imports `manifest.py` or `widget.py`, and picks up the module-level `WIDGET_FEATURE`. The result is `lru_cache`d.

Currently `src/tabs/image_compare/canvas/features/` is registered as a feature package (`tabs/image_compare/tab.py`). Within a registered package, no per-feature registration is needed: drop a folder with a `WIDGET_FEATURE` constant, it's live.

## Lookup API (`widget_registry.py`)

```python
get_canvas_feature_command_by_alias(capability_id: str) -> Callable | None
    # The 95% case. Returns the callable, or None if alias is unknown.

get_canvas_feature_command(feature_name: str, command_id: str) -> Callable | None
    # When you already know the feature and command (rare in shared code).

get_canvas_feature_commands_by_id(command_id: str) -> tuple[Callable, ...]
    # Returns the callable from EVERY feature that defines this command_id.
    # Used when shared code needs to broadcast (e.g. "all features: clear cache").

get_canvas_feature_command_aliases() -> dict[str, tuple[str, str]]
    # Full table — debugging only.
```

All lookups are `lru_cache`d (typically size 128 or 1).

## Calling pattern (shared code)

```python
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias

cmd = get_canvas_feature_command_by_alias("overlay.enabled")
if cmd is not None:
    enabled = cmd(store)
```

Always check for `None`. A missing alias means a feature was removed/renamed — graceful degradation is the contract.

The handler signature is **feature-defined**. Most take `store` as the first arg, but action-style commands take `(store, **kwargs)`:

```python
set_thickness = get_canvas_feature_command_by_alias("guides.set_thickness")
if set_thickness is not None:
    set_thickness(store, value=4)
```

Read the feature's `build_commands()` to know the exact signature.

## Naming conventions

Inspect existing aliases for the pattern:

- `<feature>.enabled` / `<feature>.is_horizontal` — read-only queries returning bool
- `<feature>.set_<field>` — write-side commands
- `<feature>.toggle_<field>` — boolean toggle
- `<feature>.active_<thing>` — query for the currently-active sub-instance
- `<feature>.settings.<thing>` — entry point for the settings dialog binding
- `<feature>.widget_state` — full state snapshot for the feature

Pick something parallel when adding a new alias — don't invent a new top-level namespace.

## Uniqueness

`get_canvas_feature_command_aliases()` raises `ValueError` if two features register the same `capability_id`. The check fires at first access (import time of the first caller), so collisions surface immediately on startup.

## Extension recipe — adding an alias

You want shared code (or another feature) to be able to call `"magnifier.reset_to_defaults"`.

1. In the feature's `widget.py` (or wherever you build commands), add the command:
   ```python
   def _build_commands():
       return {
           ...
           "viewport.reset_to_defaults": lambda store: _reset_magnifier(store),
       }
   ```
2. Add the alias entry to the feature's `command_aliases` tuple:
   ```python
   MAGNIFIER_COMMAND_ALIASES = (
       ...
       CanvasFeatureCommandAlias("magnifier.reset_to_defaults", "viewport.reset_to_defaults"),
   )
   ```
3. Wire the alias tuple on `WIDGET_FEATURE`:
   ```python
   WIDGET_FEATURE = CanvasWidgetFeature(
       name="magnifier",
       build_commands=_build_commands,
       command_aliases=MAGNIFIER_COMMAND_ALIASES,
       ...
   )
   ```
4. Done — callers can now `get_canvas_feature_command_by_alias("magnifier.reset_to_defaults")(store)`.

## When NOT to use aliases

Aliases are for **shared (non-feature) code** to call **into a feature**. Inside a feature, just call your own functions directly. Don't go alias → registry → callable when you're already in `magnifier/*`.

## See also

- [QRHI_CANVAS_FEATURES.md](QRHI_CANVAS_FEATURES.md) — the broader canvas-feature system; aliases are one of several contribution surfaces
- [CONTRACTS.md](CONTRACTS.md) — why "zero direct feature imports in shared code" exists
- `src/tabs/image_compare/canvas/features/_template/` — copyable starter feature
