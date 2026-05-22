# Canvas Features Architecture

How canvas-related functionality is organized and how to add new features.

See also: [Scene Recomposition Plan](./SCENE_RECOMPOSITION_PLAN.md)

## Quick Start

1. Copy `src/ui/canvas_features/_template/` to `src/ui/canvas_features/<your_feature>/`
2. Rename `_template` to your feature name in `widget.py` (`name=` field)
3. Add your logic
4. Done — all registries auto-discover it

No central files need editing. Packages starting with `_` are excluded from auto-discovery.

## Top-level Split

### 1. Canvas infrastructure (`src/ui/canvas_infra/`)

The framework layer. Owns scene contracts, feature registries, scene builder/composer, apply pipeline, hit-test routing, viewport contracts, zoom/pan/split state and math, GL scene contracts.

Does not own feature business logic.

Key files:
- `scene/feature_contract.py` — `CanvasSceneFeature`
- `scene/widget_contract.py` — `CanvasWidgetFeature`, `CanvasFeatureProperty`
- `scene/feature_registry.py` — auto-discovers `manifest.py`, fallback `feature.py`
- `scene/widget_registry.py` — auto-discovers `manifest.py`, fallback `widget.py`
- `scene/gl_pass_contract.py` — `CanvasGLRenderPass`, `SceneVisibility`, single-preview helpers
- `scene/property_access.py` — shared property read/write/persistence
- `scene/pipeline.py` — ordered build/apply/hit-test pipelines
- `scene/builder.py` — builds `CanvasSceneGraph`
- `scene/apply.py` — applies built scene to canvas runtime
- `scene/hit_test.py` — routes hit-testing through registered features
- `scene/stacking_policy.py` — `CanvasStackRole`, central ordering tables
- `viewport/contract.py` — viewport feature contract
- `viewport/state.py` — viewport runtime state accessors
- `viewport/zoom.py` — zoom/pan/split implementation

### 2. Canvas features (`src/ui/canvas_features/<name>/`)

Editor-facing canvas features (magnifier, divider, guides, capture, filename_overlay). Each keeps its scene logic, state logic, and widget/reducer integration in its own folder.

### 3. Canvas presentation (`src/ui/canvas_presentation/`)

Not a feature home. Used for live store snapshots, render/export-facing store transformation, canvas surface integration. Feature-specific helpers should not live here.

### 4. GL canvas renderer (`src/ui/widgets/gl_canvas/`)

Renderer backend, not a feature home. Owns GL context setup, VAO/VBO, texture upload/readback, renderer-facing consumption of `GLRenderScene`/`GLRenderRuntimeContext`, base canvas shader source, feature GL pass discovery and dispatch loop.

Shader ownership:
- `shader_sources/base.py` — main canvas background, split/channel/diff modes
- `shader_sources/common.py` — shared shader prolog helpers only
- Feature shaders live in `canvas_features/<name>/gl_passes.py`, not here

## Package Structure

```
src/ui/canvas_features/<name>/
  __init__.py
  manifest.py          # REQUIRED: exports WIDGET_FEATURE and/or FEATURE
  widget.py            # CanvasWidgetFeature definition
  feature.py           # CanvasSceneFeature definition (if scene-participating)
  gl_passes.py         # GL_RENDER_PASSES list (if rendering)
  state.py             # Feature-local state helpers
  store.py             # Feature-owned store/service helpers
  commands.py          # Command handlers
  bounds.py            # Feature-specific geometry helpers
  properties.py        # Extracted feature property schema
  toolbar.py           # Toolbar bindings and sync helpers
  settings_bindings.py # Settings event integration
  runtime_hooks.py     # Render-scene override and runtime payload helpers
  workers/             # Optional: async compute pipelines (3+ files)
```

## Auto-Discovery

| Registry | Looks for | In module |
|---|---|---|
| `widget_registry` | `WIDGET_FEATURE: CanvasWidgetFeature` | `manifest.py` or `widget.py` |
| `feature_registry` | `FEATURE: CanvasSceneFeature` | `manifest.py` or `feature.py` |
| `gl_pass_registry` | `GL_RENDER_PASSES: list[CanvasGLRenderPass]` | `gl_passes.py` |

## Current Feature Status

| Feature | Scene | Widget | Status |
|---|---|---|---|
| `magnifier` | `manifest.py` | `manifest.py` | decomposed |
| `divider` | `manifest.py` | `manifest.py` | decomposed |
| `guides` | `manifest.py` | `manifest.py` | decomposed |
| `capture` | `manifest.py` | `manifest.py` | decomposed |
| `filename_overlay` | none | `manifest.py` | GL pass + widget feature |
| `paste_overlay` | none | `manifest.py` | transitional widget-owned overlay |

Runtime degradation: missing feature packages are ignored; missing toolbar bindings disable controls; unavailable capabilities show a warning instead of crashing.

## Contracts

### CanvasWidgetFeature (`widget_contract.py`)

Presentation-layer contract.

Required fields:

| Field | Type | Purpose |
|---|---|---|
| `name` | `str` | Unique feature identifier |
| `reduce_view_state` | `fn(ViewState, Action) -> ViewState` | Handle view state actions |
| `reduce_render_config` | `fn(RenderConfig, Action) -> RenderConfig` | Handle render config actions |

Optional fields:

| Field | Purpose |
|---|---|
| `reduce_interaction_state` | Handle interaction-related actions |
| `reduce_geometry_state` | Handle geometry-related actions |
| `build_commands` | `fn() -> dict[str, handler]` — register callable commands |
| `command_aliases` | `tuple[CanvasFeatureCommandAlias, ...]` — capability aliases |
| `build_properties` | Register keyframe-animatable properties |
| `build_toolbar_bindings` | Connect toolbar controls |
| `build_settings_event_bindings` | React to settings dialog events |
| `build_render_scene_overrides` | Contribute data to GL render scene |
| `prepare_worker_viewport` | Prepare viewport state for background workers |
| `apply_plan_runtime_overlay` | Apply overlays from render plan |
| `apply_live_runtime_overlay` | Apply live overlays during rendering |
| `reducer_order` | Sort order for reducer dispatch (default 100) |
| `property_order` | Sort order for property listing (default 100) |

### CanvasSceneFeature (`feature_contract.py`)

Scene-graph contract. Only needed if feature participates in scene (hit-testing, stacking, scene-level apply).

| Field | Type | Required | Purpose |
|---|---|---|---|
| `name` | `str` | yes | Must match widget feature name |
| `build_primary` | `fn(ctx) -> tuple[SceneObject, ...]` | yes | Create scene objects |
| `build_overlay` | `fn(graph, ctx) -> tuple[SceneObject, ...]` | yes | Create overlay objects |
| `apply` | `fn(graph, ctx) -> None` | yes | Apply scene state to viewport |
| `hit_test` | `fn(graph, point) -> SceneObject\|None` | no | Find object at position |
| `z_order` | `CanvasFeatureZOrder` | no | Stacking role |

Phase order controls when a feature runs: `primary_order`, `overlay_order`, `apply_order`, `hit_order`.

Canvas z-level controls scene composition: `CanvasFeatureZOrder.layer`, `.priority`, optional `active_bias`, `always_on_top`, `selectable_when_hidden`.

`CanvasSceneApplyContext` carries `scene_visibility`. Feature `apply()` code should use it when deciding whether to populate interactive-only runtime payloads.

### CanvasGLRenderPass (`gl_pass_contract.py`)

Set `stack_role` and `visibility` — never hardcode `layer`/`priority`.

```python
from ui.canvas_infra.scene.gl_pass_contract import CanvasGLRenderPass, SceneVisibility
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole

class MyPass(CanvasGLRenderPass):
    stack_role = CanvasStackRole.VIEW_ANNOTATION
    visibility = SceneVisibility.ALL

    def initialize(self, widget) -> None: ...
    def should_paint(self, ctx) -> bool: ...
    def paint(self, widget, ctx) -> None: ...
    def cleanup(self, widget) -> None: ...
```

Scene visibility:

| Visibility | Meaning |
|---|---|
| `SceneVisibility.INTERACTIVE` | live editing canvas only |
| `SceneVisibility.EXPORT` | export/video/offscreen rendering |
| `SceneVisibility.PREVIEW` | preview surfaces |
| `SceneVisibility.ALL` | visible in every scene mode |

Rules:
- mode filtering is handled centrally by the render executor
- `should_paint()` should check data availability and feature-local presentation rules, not export-vs-interactive policy
- interactive-only payloads should usually be suppressed earlier in feature `apply()`
- single-image preview is not a central render-executor flag anymore; if a pass should be silent in that mode, it should decide that locally in `should_paint()`

Available roles:

| Role | GL Phase | Use case |
|---|---|---|
| `UNDERLAY_SPLIT` | IMAGE_DECORATION | Split/divider line |
| `IMAGE_OVERLAY_CONTENT` | IMAGE_ANNOTATION | Magnifier GPU content |
| `ANNOTATION_RING` | VIEW_ANNOTATION | Capture rings |
| `ANNOTATION_BORDER` | VIEW_ANNOTATION | Borders, occluded arcs |
| `ANNOTATION_GUIDE` | VIEW_ANNOTATION | Guide lines |
| `HUD_LABEL` | HUD | Filename overlay, status text |
| `TRANSIENT_PREVIEW` | HUD | Preview elements |
| `INTERACTION_HANDLE` | VIEW_ANNOTATION | Drag handles |
| `DEBUG_VIS` | DEBUG | Debug visualization |

Pass instances are long-lived (one per session). Store compiled `QOpenGLShaderProgram` objects as instance attributes, not on the widget.

### CanvasFeatureProperty (`widget_contract.py`)

Canonical schema for a canvas feature property. Describes: `id`, `label`, `kind`, `channels`, `group_id`, `group_label`, `setting_key`, `read_snapshot`, `write_snapshot`, optional serialization.

Shared source of truth for: video editor keyframe tracks, settings load/save, manual color/thickness/visibility mutations. Describe a property once — don't wire it separately for keyframes and settings.

### Command Aliases

Shared code must not use `get_canvas_feature_command("feature_name", "cmd")`. Instead:

1. Feature declares aliases in `widget.py`:
   ```python
   COMMAND_ALIASES = (
       CanvasFeatureCommandAlias("my_feature.do_thing", "runtime.do_thing"),
   )
   ```

2. Shared code uses the capability alias:
   ```python
   cmd = get_canvas_feature_command_by_alias("my_feature.do_thing")
   if cmd is not None:
       cmd(...)
   ```

If the feature is absent, returns `None`.

## Viewport Change Contract

When feature commands modify state that affects UI rendering or panel visibility, they must emit viewport changes to notify the system.

### Pattern

All feature commands that modify state should follow this pattern:

```python
def viewport_set_feature_property(store, value):
    if store is None or getattr(store, "viewport", None) is None:
        return None

    # Modify state via store service
    result = StoreService(store).update_property(value)

    # Always emit full viewport change after state modification
    if hasattr(store, 'emit_viewport_change'):
        store.emit_viewport_change()

    return result
```

### Rules

1. **Always emit after state changes** — UI panels and buttons won't update without viewport change notification
2. **Check for `emit_viewport_change` method** — during initialization, store may be wrapped in `StoreProxy` which lacks this method
3. **Use full viewport change** — call `emit_viewport_change()` without subdomain parameter, not `emit_viewport_change("interaction")`
4. **Don't emit during read-only operations** — queries and hit-tests should not emit changes

### Why This Matters

Without viewport changes:
- Toggle buttons won't update their visual state
- Toolbar panels won't appear/disappear
- Capture area highlights won't recalculate
- User must move mouse to trigger re-render

With viewport changes:
- All UI updates happen immediately
- State changes are visible instantly
- No need for user interaction to see feedback

## Canvas Layout Contract

### Problem

The render/export path mixes three coordinate spaces: base image space, virtual canvas space expanded by features, and final viewport/display space after zoom/pan. That creates late corrective steps that break the contract.

### Model

Each feature reports its layout requirement explicitly in normalized base-image coordinates.

- base comparison content occupies `x=0.0..1.0`, `y=0.0..1.0`
- a magnifier might require `x=0.4..1.5`, `y=0.5..2.0`
- the layout resolver unions those ranges into a virtual canvas

Shared types in `src/shared/rendering/layout_contract.py`:
- `NormalizedBounds` — may extend outside `0..1`
- `FeatureLayoutRequirement` — feature-owned bounds request
- `VirtualCanvasLayout` — resolved union of base content + feature requirements

Rules:
- features report geometry in base-image normalized coordinates
- the layout resolver produces virtual canvas coordinates
- viewport transform applies zoom/pan/output sizing afterwards
- placement may live in virtual-canvas space; source sampling follows feature's own semantic space
- disabling a feature suppresses its per-instance animation regardless of stored geometry tracks
- core should not invent additional feature-specific coordinate fixes after this phase

### Registration

Features register via the `render.layout_requirement` command alias. Shared builders resolve requirements through `VirtualCanvasLayout`. Old pixel padding API remains as compatibility fallback.

## GL Render Contract

Canvas features do not draw with PIL, QPainter, or CPU overlay pipeline. The render path is:

```
feature apply()
  -> runtime_state fields
  -> build_render_runtime_context()  [render_context.py]
  -> GLRenderRuntimeContext (ctx)
  -> CanvasGLRenderPass.paint(widget, ctx)  [canvas_features/*/gl_passes.py]
```

Feature-specific `GLRenderScene` values come from `WIDGET_FEATURE.build_render_scene_overrides(store)`. The GL scene builder aggregates these but must not import feature state modules directly.

Exception: SSIM map is CPU-generated/cached and uploaded as a texture. This is analysis data, not a CPU canvas renderer.

Do not reintroduce: `RenderingPipeline`, PIL/ImageDraw/QPainter canvas overlays, CPU fallback workers for static canvas rendering, GPU failure fallback to CPU for canvas/video snapshots.

## Scene Pipeline

### Build (`scene/builder.py`)
- resolves canvas bounds
- creates `CanvasSceneBuildContext`
- calls every registered `build_primary`
- creates base `CanvasSceneGraph`
- calls every registered `build_overlay`
- returns full scene graph

### Apply (`scene/apply.py`)
- creates `CanvasSceneApplyContext`
- passes `scene_visibility` into feature `apply()`
- calls every registered feature applier to populate runtime overlay state

### Hit-test (`scene/hit_test.py`)
- routes point through registered hit-testers in pipeline order
- returns first match

## Keyframing Rules

Feature-owned keyframe adapters treat time as global across the whole recording.

- feature activation/enabled state must be keyed explicitly
- per-instance/property tracks must not resurrect a feature after its global enabled track is `false`
- global feature switches belong in the feature property/schema layer
- dynamic/per-instance adapters apply geometry/style only when the feature is enabled in the snapshot

## Snapshot Renderer Notes

Preferred export/video direction:
- one snapshot-driven render-plan builder
- one GL/offscreen renderer backend
- multiple snapshot producers (`live store -> snapshot`, `timeline -> snapshot(t)`)

Image export preview/final and video preview/export differ by snapshot source and target surface, not by feature-specific scene assembly.

## Source of Truth Rules

### Feature-owned state
- lives in `view_state.canvas_widget_state["<feature_name>"]`
- no second flat compatibility copy in `ViewState`
- `RenderConfig` is for infrastructure, not per-feature ownership

### No silent fallback writes
- read-only fallback is acceptable
- write-path fallback is not (fail fast or no-op explicitly)
- matters especially for multi-instance features

### Feature geometry belongs to the feature
- feature-specific bounds helpers go in the feature folder, not `canvas_presentation`

## Anti-patterns

- Adding feature logic to `canvas_infra`
- Adding new central `if feature == ...` logic
- Duplicating state in both feature-owned storage and flat `ViewState`
- Describing the same property separately for keyframes and settings/UI
- Putting feature geometry helpers into `canvas_presentation`
- Letting write paths silently fall back to a different instance
- Treating viewport foundation as a normal editor feature
- Adding PIL/QPainter/CPU fallback render paths for GL features
- Recreating a central shader facade instead of feature-owned `gl_passes.py`
- Naming infrastructure stack layers after concrete features
- Importing feature state directly from `scene.py` instead of using overrides
- Placing feature shaders under `shader_sources/`
- Storing shader programs on the widget instead of on `CanvasGLRenderPass`
- Reintroducing executor-level special flags like `hide_in_single_preview`
- Using feature-local mode services to decide export/interative visibility when `SceneVisibility` already expresses it

## Checklist

Before merging a new canvas feature:

- [ ] Package in `src/ui/canvas_features/<name>/`
- [ ] `manifest.py` exports `WIDGET_FEATURE` (and optionally `FEATURE`)
- [ ] `name` field is unique and does not start with `_`
- [ ] Reducers are no-op if feature has no state actions
- [ ] Commands exposed via aliases (not direct feature-name lookups)
- [ ] **All state-modifying commands emit viewport changes** (see Viewport Change Contract)
- [ ] GL passes use `stack_role`, not hardcoded `layer`/`priority`
- [ ] GL passes set `visibility` explicitly
- [ ] Scene z_order uses `stack_role` via `CanvasFeatureZOrder`
- [ ] No imports of this feature in shared `ui/`, `events/`, or `plugins/` code
- [ ] User-editable values declared as `CanvasFeatureProperty`
- [ ] No central registry file was edited
- [ ] Feature-specific helpers not in `canvas_presentation`
- [ ] Shader code in `gl_passes.py` alongside draw calls
- [ ] No new shader source files under `shader_sources/`

## Examples

- `magnifier/` — largest: scene, state, store, mode, widget, geometry, workers
- `divider/` — small feature
- `guides/` — overlay with owner-state, actions, settings/keyframe properties, render payload
- `capture/` — small overlay with settings/keyframe properties and render payload
- `_template/` — copyable starter template
- `canvas_infra/viewport/` — infrastructure (not a consumer feature)
