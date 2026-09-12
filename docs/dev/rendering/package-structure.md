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
[render-pass-contract.md](render-pass-contract.md)). Only concrete features
are tab-owned; infrastructure is not.

## Auto-Discovery

| Registry | Looks for | In module |
|---|---|---|
| `widget_registry` | `WIDGET_FEATURE: CanvasWidgetFeature` | `manifest.py` or `widget.py` |
| `feature_registry` | `FEATURE: CanvasSceneFeature` | `manifest.py` or `feature.py` |
| `pass_registry` (QRhi) | `RENDER_PASSES: list[CanvasRenderPass]` | `passes.py` |

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
name and silently skips features where the import fails). Everything else
is free to move into subpackages once a feature outgrows a flat file list
(see `magnifier/` for the reference layout). Group by concern, not by
file-name prefix:

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
| `multi_compare` | `grid_dividers` | none | `manifest.py` | decomposed; render pass + widget feature + gesture bindings |
| `multi_compare` | `layer_labels` | none | `manifest.py` | root-contract-only, nothing to decompose; render pass + widget feature |
| `multi_compare` | `drag_drop_overlay` | none | `manifest.py` | decomposed; render pass + widget feature + gesture bindings |

`multi_compare` participates in the same `register_canvas_widget_feature_package`
/ `register_canvas_scene_feature_package` / `register_canvas_render_pass_feature_package`
discovery as `image_compare` (see `docs/dev/MULTI_COMPARE_QRHI_REFACTOR.md` for
background) — `image_compare` is not the only tab following this contract.
`multi_compare`'s three features have no scene-feature package (`scene: none`)
because their behavior is pure render-pass + gesture, with no scene-graph
object to compose; its base image draw (`BaseImagesPass`) intentionally has
no feature package at all — it stays core-owned renderer code, same as
`image_compare`'s own base-image draw (see that doc's Decisions log, "A6").
`multi_compare`'s mouse-gesture resolution does not reuse this package's
shared `GestureResolver` (`scene/gesture_resolver.py`) — it has its own local
equivalent, `tabs/multi_compare/canvas/gesture_resolver.py`, because
`multi_compare` uses a fully local, tab-scoped store (`MultiCompareStore`)
rather than the global app store `GestureResolver.resolve_press` derives its
registry lookup from; see that module's docstring and
`MULTI_COMPARE_QRHI_REFACTOR.md`'s D4 entry.

Runtime degradation: missing feature packages are ignored; missing toolbar
bindings disable controls; unavailable capabilities show a warning instead of
crashing.
