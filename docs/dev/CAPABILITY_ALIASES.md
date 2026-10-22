# Capability aliases

Canvas features expose their behavior to shared (non-feature) code through **capability aliases** — string IDs like `"overlay.enabled"` or `"guides.set_thickness"`. Shared code looks up a callable by alias and invokes it; the feature can be renamed, moved, or replaced without rippling through callers.

This is the mechanism behind ImgSLI's "zero direct imports of features in shared code" rule.

## Files

| Path | Role |
|---|---|
| `src/ui/canvas_infra/scene/widget_contract.py` | `CanvasWidgetFeature`, `CanvasFeatureCommandAlias` dataclasses |
| `src/ui/canvas_infra/scene/registry.py` | discovery, lookup, alias resolution — one `CanvasFeatureRegistry` per tab type |
| `src/tabs/image_compare/canvas/features/<name>/widget.py` (or `manifest.py`) | per-feature `WIDGET_FEATURE = CanvasWidgetFeature(...)` |

## The contract (`widget_contract.py`)

```python
@dataclass(frozen=True, slots=True)
class CanvasFeatureCommandAlias:
    capability_id: str   # public string callers use:   "overlay.enabled"
    command_id: str      # private id inside the feature: "query.enabled"

@dataclass(frozen=True, slots=True)
class CanvasWidgetFeature:
    name: str                                       # e.g. "magnifier"
    reduce_view_state: ReduceViewStateFn            # required, positional
    reduce_render_config: ReduceRenderConfigFn      # required, positional
    # every build_* hook below is optional (default None):
    build_commands: Callable[[], dict[str, Handler]] | None = None
    command_aliases: tuple[CanvasFeatureCommandAlias, ...] = ()
    # ... also build_properties / build_toolbar_bindings / build_gesture_bindings /
    # build_settings_event_bindings / build_context_menu_zones / build_state_* /
    # prepare_worker_viewport / apply_*_runtime_overlay (widget_contract.py:180-203)
```

`reduce_view_state` and `reduce_render_config` are mandatory and positional —
a feature without them cannot be constructed. No `build_*` hook is mandatory;
a feature that only reduces state declares none.

Alias resolution is two-step:
1. `capability_id` → `(feature_name, command_id)` via the alias table
2. `(feature_name, command_id)` → callable via `build_commands()`

The split lets a feature reorganize internal commands without changing public IDs, and lets two features expose the same `command_id` name (e.g. both define `"query.enabled"`) without collision.

## Discovery

The registry is **per tab type**: `get_canvas_registry(tab_type)`
(`registry.py:380`) returns that tab's single `CanvasFeatureRegistry`, and
`register_canvas_feature_package(tab_type, package)` (`registry.py:388`)
registers its feature package. Two tabs register today:

- `register_canvas_feature_package("image_compare", …)` — `src/tabs/image_compare/tab.py:483`
- `register_canvas_feature_package("multi_compare", …)` — `src/tabs/multi_compare/tab.py:282`

`get_widget_features()` (`registry.py:87`, `lru_cache(maxsize=1)`) walks the
registered packages with `pkgutil`, imports `<feature>/manifest.py` (falling
back to `<feature>/widget.py`) and picks up the module-level `WIDGET_FEATURE`.
Within a registered package, no per-feature registration is needed: drop a
folder with a `WIDGET_FEATURE` constant and it is live.
`src/tabs/image_compare/canvas/registry.py:20` is the tab's thin accessor
(`registry()` → `get_canvas_registry("image_compare")`).

## Lookup API (`src/ui/canvas_infra/scene/registry.py`)

There are **no module-level lookup functions** — the old
`widget_registry.py` was deleted in `b981d692` and its five helpers became
methods on `CanvasFeatureRegistry`:

```python
registry = get_canvas_registry(tab_type)   # "image_compare" | "multi_compare"

registry.get_feature_command_by_alias(capability_id: str) -> Callable | None   # :273, lru 128
    # The 95% case. Returns the callable, or None if alias is unknown.

registry.get_feature_command(feature_name: str, command_id: str) -> Callable | None   # :269, lru 128
    # When you already know the feature and command (rare in shared code).

registry.get_feature_commands_by_id(command_id: str) -> tuple[Callable, ...]   # :281, lru 128
    # Returns the callable from EVERY feature that defines this command_id.
    # Used when shared code needs to broadcast (e.g. "all features: clear cache").

registry.get_feature_command_aliases() -> dict[str, tuple[str, str]]   # :152, lru 1
    # Full table — debugging only.
```

All lookups are `lru_cache`d (sizes 1 / 128, per the annotations above) and
`register_package` clears them wholesale (`_clear_caches`, `registry.py:43`).

## Calling pattern (shared code)

```python
from ui.canvas_infra.scene.registry import get_canvas_registry

cmd = get_canvas_registry("image_compare").get_feature_command_by_alias("overlay.enabled")
if cmd is not None:
    enabled = cmd(store)
```

Inside `src/tabs` prefer the importable wrappers in
`src/tabs/_shared/canvas.py` — `get_canvas_feature_command_by_alias` (`:60`)
and `execute_canvas_feature_alias` (`:68`) — which resolve the `image_compare`
registry for you. They are tab-side convenience helpers, not registry module
functions.

Always check for `None`. A missing alias means a feature was removed/renamed — graceful degradation is the contract.

The handler signature is **feature-defined**. Most take `store` as the first arg, but action-style commands take `(store, **kwargs)`:

```python
set_thickness = get_canvas_registry("image_compare").get_feature_command_by_alias("guides.set_thickness")
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

`get_feature_command_aliases()` raises `ValueError` if two features register the same `capability_id`. The check runs the first time the (cached) alias table is built, i.e. on the first lookup after startup, so a collision surfaces immediately rather than silently shadowing one feature.

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
4. Done — callers can now do
   `get_canvas_registry("image_compare").get_feature_command_by_alias("magnifier.reset_to_defaults")(store)`.
   Inside `src/tabs`, `execute_canvas_feature_alias("magnifier.reset_to_defaults", store)` is the same lookup.

## When NOT to use aliases

Aliases are for **shared (non-feature) code** to call **into a feature**. Inside a feature, just call your own functions directly. Don't go alias → registry → callable when you're already in `magnifier/*`.

## See also

- [rendering/index.md](rendering/index.md) — the broader canvas-feature system; aliases are one of several contribution surfaces
- [CONTRACTS.md](CONTRACTS.md) — why "zero direct feature imports in shared code" exists
- `src/tabs/image_compare/canvas/features/_template/` — copyable starter feature
