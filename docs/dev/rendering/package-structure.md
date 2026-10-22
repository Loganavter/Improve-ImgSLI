# Package Structure

```
src/tabs/<tab>/canvas/features/<name>/
  __init__.py
  manifest.py          # exports FEATURE / WIDGET_FEATURE
  passes.py             # RENDER_PASSES: list[CanvasRenderPass]
  feature.py             # CanvasSceneFeature, if scene-participating
  widget.py              # CanvasWidgetFeature definition
  state.py               # feature-local state helpers
  properties.py          # CanvasFeatureProperty schema
  actions.py / commands.py / events.py / gestures.py / interaction.py
  runtime_hooks.py        # render-scene override / runtime payload helpers
  settings_bindings.py
  toolbar.py
  shaders/                # .vert/.frag sources + compiled .qsb, feature-owned
```

Feature ownership is per-tab (`src/tabs/<tab>/canvas/features/<name>/`) — a
tab owns its own feature set instead of every feature being visible to every
tab by default. `canvas_infra` (`scene/`, `viewport/`, `stacking_policy.py`,
the pass/feature contracts) does **not** live per-tab — it stays a shared
library under `src/ui/canvas_infra/`, imported the same way by every tab (see
the `from ui.canvas_infra.scene.pass_contract import ...` example in
[render-pass-contract.md](render-pass-contract.md) — `CanvasRenderPass` at
`src/ui/canvas_infra/scene/pass_contract.py`,
`CanvasRenderPassBase` for legacy GL). Shared presentation/composition lives in
`src/ui/canvas_presentation/` (`plan.py` `CanvasRenderPlan`, `composition.py`
`CompositionPlan`/`ResolvedComposition` — see [rendering-model.md](rendering-model.md)
and [coordinate-systems.md](coordinate-systems.md)); single geometry owner for
comparison letterbox is `src/tabs/image_compare/canvas/texture_parts/base_images.py`
(`update_common_letterbox_geometry`) via
`src/ui/canvas_infra/scene/frame_geometry.py::resolve_canvas_content_geometry`.
Only concrete features are tab-owned; infrastructure is not.

## Auto-Discovery

| Discovery | Looks for | In module |
|---|---|---|
| `CanvasFeatureRegistry.get_widget_features` | `WIDGET_FEATURE: CanvasWidgetFeature` (`src/ui/canvas_infra/scene/widget_contract.py`) | `manifest.py` or `widget.py` |
| `CanvasFeatureRegistry.get_scene_features` | `FEATURE: CanvasSceneFeature` (`src/ui/canvas_infra/scene/feature_contract.py`) | `manifest.py` or `feature.py` |
| `CanvasFeatureRegistry.get_render_passes` | `RENDER_PASSES: list[CanvasRenderPass]` (`src/ui/canvas_infra/scene/pass_contract.py`) | `passes.py` |

One registry class serves a tab's whole feature set
(`src/ui/canvas_infra/scene/registry.py`); `get_canvas_registry(tab_type)` keeps
one instance per tab type and `register_canvas_feature_package(tab_type,
package)` adds a feature package to it (called once per tab at startup, e.g.
`src/tabs/image_compare/tab.py` and `src/tabs/multi_compare/tab.py`).

Never hand-wire a pass into a central file. Export it from your feature's
`passes.py` and it's discovered.

## Splitting a large feature into subpackages

`manifest.py`, `widget.py`, `feature.py`, `properties.py`,
`settings_bindings.py`, `constants.py`, `runtime_hooks.py`, `passes.py`,
`__init__.py` must stay at the feature's top level — auto-discovery depends
on finding them there by exact import path
(`<feature_pkg>.<name>.passes`, `<feature_pkg>.<name>.manifest`, etc. — see
`CanvasFeatureRegistry._iter_feature_modules` in
`src/ui/canvas_infra/scene/registry.py`, which imports these by hardcoded
name). Only "this package ships no such module" is a skip: a
`ModuleNotFoundError` raised *inside* an existing module propagates out of the
registry (`raise`, on purpose — a silently skipped feature drops its passes
from every frame with no error). A moved contract file therefore fails loudly,
not quietly. Everything else is free to move into subpackages once a feature
outgrows a flat file list (see `magnifier/` for the reference layout). Group by
concern, not by file-name prefix:

| Subpackage | Contents |
|---|---|
| `state/` | store, feature-local state, models, runtime state, snapshot store, mode |
| `render/` | pass implementations and helpers referenced by the root `passes.py` (pass classes, overlay/plan-overlay, shader layout, tile capture) |
| `geometry/` | bounds, layout plan, drawing coords, hit-test, generic geometry math |
| `input/` | gestures, interaction, keyboard movement, actions, events |
| `scene/` | scene apply/build/objects |

Existing `commands/`, `reducers/`, `toolbar/`, `workers/`, `resources/`,
`shaders/` subpackages already follow this pattern and don't need touching.

When doing this split, always import the moved modules by their **fully
qualified absolute path**
(`tabs.<tab>.canvas.features.<name>.<subpkg>.<module>`), never by relative
import — relative imports break silently when a file's depth in the tree
changes, while absolute imports fail loudly (`ImportError`) if a path is
wrong.

Also check for `Path(__file__).parent`-style lookups (shader dirs, resource
dirs) in any module you move — these silently point at the wrong directory
once the file's depth in the tree changes, with no import error to catch it.

## Current Feature Status

| Tab | Feature | Scene | Widget | Status |
|---|---|---|---|---|
| `image_compare` | `magnifier` | `manifest.py` | `manifest.py` | decomposed |
| `image_compare` | `divider` | `manifest.py` | `manifest.py` | decomposed |
| `image_compare` | `guides` | `manifest.py` | `manifest.py` | decomposed |
| `image_compare` | `capture` | `manifest.py` | `manifest.py` | decomposed |
| `image_compare` | `filename_overlay` | none | `manifest.py` | decomposed; render pass + widget feature |
| `image_compare` | `drag_drop_overlay` | none | `manifest.py` | render pass + widget feature; only `keepwarm.py`/`render/` split out |
| `multi_compare` | `grid_dividers` | none | `manifest.py` | decomposed; render pass + widget feature + gesture bindings |
| `multi_compare` | `layer_labels` | none | `manifest.py` | root-contract-only, nothing to decompose; render pass + widget feature |
| `multi_compare` | `drag_drop_overlay` | none | `manifest.py` | decomposed; render pass + widget feature + gesture bindings |
| `multi_compare` | `focus_dim` | none | none | render pass only (`passes.py` + `shaders/`, no manifest) |

`multi_compare` participates in the same
`register_canvas_feature_package(tab_type, package)` discovery as
`image_compare` (`src/tabs/multi_compare/tab.py`) — `image_compare` is not the
only tab following this contract.
`multi_compare`'s four features have no scene-feature package (`scene: none`)
because their behavior is pure render-pass + gesture, with no scene-graph
object to compose; its base image draw (`src/tabs/multi_compare/scene/passes/base_images.py::BaseImagesPass`)
intentionally has no feature package at all — it stays core-owned renderer
code, same as `image_compare`'s own base-image draw.
`multi_compare`'s mouse-gesture resolution does not reuse this package's
shared `GestureResolver` (`scene/gesture_resolver.py`) — it has its own local
equivalent, `tabs/multi_compare/canvas/gesture_resolver.py`, because
`multi_compare` uses a fully local, tab-scoped store (`MultiCompareStore`)
rather than the global app store the shared resolver's `_session_type()` reads
(`store.get_active_workspace_session().session_type`) to pick a registry.

Runtime degradation: missing feature packages are ignored; missing toolbar
bindings disable controls; unavailable capabilities show a warning instead of
crashing.