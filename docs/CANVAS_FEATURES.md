# Canvas Features Architecture

This document describes how canvas-related functionality is organized in the project and how to add new features without scattering code across unrelated layers.

See also:

- [Scene Recomposition Plan](./SCENE_RECOMPOSITION_PLAN.md)

`CANVAS_FEATURES.md` describes the current structure.
`SCENE_RECOMPOSITION_PLAN.md` describes the target architecture for removing feature-name coupling from shared layers and making features optional at runtime.

## Current Status

The preferred assembly style is now:

- `manifest.py` as the package entrypoint
- `build_scene_feature()` in `feature.py` when a scene feature exists
- `build_widget_feature()` in `widget.py` when a widget feature exists
- command aliases for shared capability lookup instead of direct feature-name calls where possible

Current feature status:

| Feature | Scene | Widget | Status |
|---|---|---|---|
| `magnifier` | `manifest.py` | `manifest.py` | decomposed |
| `divider` | `manifest.py` | `manifest.py` | decomposed |
| `guides` | `manifest.py` | `manifest.py` | decomposed |
| `capture` | `manifest.py` | `manifest.py` | partial migration |
| `filename_overlay` | none | `manifest.py` | partial migration |

Runtime degradation rules already in place:

- missing feature packages are ignored by scene/widget registries
- missing toolbar bindings disable the corresponding controls during toolbar state sync
- user-triggered calls into unavailable toolbar capabilities show a local warning instead of crashing startup or idle render flow

## Goals

- One clear home for each canvas feature.
- No legacy bridges or shadow sources of truth.
- Canvas visuals are rendered through the GL scene/shader pipeline. Do not add CPU/PIL render fallbacks for canvas features.
- Scene build/apply/hit-test should be registered automatically.
- Reducer, keyframes, settings persistence, and manual property UI should belong to the feature that owns the state.
- Viewport foundation such as zoom/pan must stay in canvas infrastructure, not in a consumer feature.

## Top-level split

There are three different categories of code:

### 1. Canvas infrastructure

Path:
- `src/ui/canvas_infra/scene`
- `src/ui/canvas_infra/viewport`

This is the framework layer for the canvas.

It owns:
- scene contracts
- feature registries
- scene builder/composer
- scene apply pipeline
- hit-test routing
- viewport contracts
- zoom/pan/split state and math
- GL scene contracts and renderer-facing scene snapshots

It does not own feature business logic.

### 2. Canvas features

Path:
- `src/ui/canvas_features/<feature_name>/`

This is for editor-facing canvas features such as:
- magnifier
- divider
- guides
- capture

Each feature should keep its scene logic, state logic, and widget/reducer integration in its own folder.

### 3. Canvas objects

Path:
- `src/canvas_objects/<object_name>/`

This is for document-backed, richer object types that are more than overlays.

Use this area when the thing has heavier object semantics: layout, editing, selection, serialization, richer keyframing behavior, and not just an overlay pass.

## Current directory model

### Canvas infra

- `src/ui/canvas_infra/scene/feature_contract.py`
  Defines `CanvasSceneFeature`.
- `src/ui/canvas_infra/scene/widget_contract.py`
  Defines `CanvasWidgetFeature` and `CanvasFeatureProperty`.
- `src/ui/canvas_infra/scene/feature_registry.py`
  Auto-discovers `ui.canvas_features.*.manifest` first, then falls back to `feature.py`.
- `src/ui/canvas_infra/scene/widget_registry.py`
  Auto-discovers `ui.canvas_features.*.manifest` first, then falls back to `widget.py`.
- `src/ui/canvas_infra/scene/property_access.py`
  Shared property read/write/persistence helpers built on feature schema.
- `src/ui/canvas_infra/scene/pipeline.py`
  Produces ordered build/apply/hit-test pipelines.
- `src/ui/canvas_infra/scene/builder.py`
  Builds `CanvasSceneGraph`.
- `src/ui/canvas_infra/scene/apply.py`
  Applies the built scene to the canvas runtime.
- `src/ui/canvas_infra/scene/hit_test.py`
  Routes hit-testing through registered feature hit-testers.
- `src/ui/canvas_infra/viewport/contract.py`
  Defines the viewport feature contract.
- `src/ui/canvas_infra/viewport/state.py`
  Owns viewport runtime state accessors.
- `src/ui/canvas_infra/viewport/zoom.py`
  Current zoom/pan/split implementation.

### Canvas features

Every feature folder may contain some or all of:

- `manifest.py`
  Preferred assembly root. Exports `FEATURE` and/or `WIDGET_FEATURE`.
- `feature.py`
  Scene build/apply/hit-test integration.
- `widget.py`
  Reducer and property schema contributions. Prefer keeping this as a thin assembly file.
- `state.py`
  Feature-owned persistent widget state.
- `store.py`
  Feature-owned store/service helpers.
- `mode.py`
  Feature policy rules.
- `bounds.py`
  Feature-specific geometry helpers.
- `gl_passes.py`
  Feature-owned GL render passes. Exports `GL_RENDER_PASSES: list[CanvasGLRenderPass]`.
  Each pass owns its own GLSL source and compiled shader programs.
  Do not place feature shaders anywhere else.
- `workers/`
  Optional subdirectory for async compute pipelines (3+ related worker files).
  Example: magnifier thumbnail workers.
- `properties.py`
  Extracted feature property schema.
- `commands.py`
  Extracted commands and queries.
- `toolbar.py`
  Toolbar bindings and sync helpers.
- `settings_bindings.py`
  Settings event integration.
- `runtime_hooks.py`
  Render-scene override and runtime payload helpers.

Example:
- `src/ui/canvas_features/magnifier/`

### Canvas presentation

Path:
- `src/ui/canvas_presentation/`

This layer is not a feature home.

It is used for:
- live store snapshots
- render/export-facing store transformation
- canvas surface integration

If a helper is specific to one feature, it should not live here.

### GL canvas renderer

Path:
- `src/ui/widgets/gl_canvas/`
- `src/ui/widgets/gl_canvas/shader_sources/`

This layer is the renderer backend, not a feature home.

It owns:
- GL context setup, VAO/VBO, and texture upload/readback infrastructure
- renderer-facing consumption of `GLRenderScene` and `GLRenderRuntimeContext`
- base canvas shader source (main image, split, diff modes)
- feature GL pass discovery and dispatch loop
- renderer utility helpers (`render_common.py`, `render_config.py`)

Shader source ownership:
- `shader_sources/base.py` — main canvas background, split/channel mode, diff modes (`highlight`, `grayscale`, `edges`).
- `shader_sources/common.py` — shared shader prolog helpers only.
- Feature shaders live in `canvas_features/<name>/gl_passes.py`, not here.

Do not add feature-specific shader source files under `shader_sources/`.
Do not recreate a monolithic `shaders.py`.

## Contracts

## GL render pass contract

`CanvasGLRenderPass` lives in `src/ui/canvas_infra/scene/gl_pass_contract.py`.

Each feature may export a module-level `GL_RENDER_PASSES` list in `gl_passes.py`.

```python
GL_RENDER_PASSES: list[CanvasGLRenderPass] = [MyPass()]
```

It provides:
- `layer: CanvasGLLayer` — render bucket (UNDERLAY / OVERLAY / OBJECT / FOREGROUND)
- `priority: int` — draw order within the layer (lower = earlier)
- `initialize(widget)` — compile shaders, allocate GL resources; called once after GL context is ready
- `should_paint(ctx) -> bool` — return False to skip this pass entirely for the frame
- `paint(widget, ctx)` — issue draw calls
- `cleanup(widget)` — release GL resources on context destruction

`CanvasGLLayer` values are generic infrastructure buckets. Do not name them after concrete features.

Pass instances are long-lived (one per session). Store compiled `QOpenGLShaderProgram` objects and
shader caches as instance attributes, not on the widget.

The registry (`gl_pass_registry.py`) auto-discovers passes from every
`ui.canvas_features.<name>.gl_passes` module, sorted by `(layer, priority)`.
Adding a new GL pass does not require editing any central file.

## Scene feature contract

`CanvasSceneFeature` lives in `src/ui/canvas_infra/scene/feature_contract.py`.

Each feature exports a module-level `FEATURE`.

It provides:
- `build_primary(context)`
- `build_overlay(scene, context)`
- `apply(scene, context)`
- optional `hit_test(scene, point)`
- `z_order`
- phase ordering fields

This is what makes a feature participate in:
- scene construction
- runtime apply
- hit testing

The registry auto-loads:
- `ui.canvas_features.<name>.manifest`
- fallback: `ui.canvas_features.<name>.feature`

So adding a new feature does not require editing a central switch.

### Render order and z-levels

There are two different ordering concepts.

Phase order controls when a feature runs:
- `primary_order`
- `overlay_order`
- `apply_order`
- `hit_order`

Canvas z-level controls where feature objects sit in the composed scene:
- `CanvasFeatureZOrder.layer`
- `CanvasFeatureZOrder.priority`
- optional flags such as `active_bias`, `always_on_top`, and `selectable_when_hidden`

`CanvasStackLayer` values are generic infrastructure buckets such as underlay, object, overlay, and foreground. They must not be named after concrete features.

Do not hardcode object stack policy as random local `z_index` values. A feature should expose its default stack policy through `FEATURE.z_order`, then object builders may derive per-object priority from that policy.

## Widget feature contract

`CanvasWidgetFeature` lives in `src/ui/canvas_infra/scene/widget_contract.py`.

Each feature may export a module-level `WIDGET_FEATURE`.

It provides:
- `reduce_view_state(view_state, action)`
- `reduce_render_config(render_config, action)`
- optional `build_properties()`
- optional `build_toolbar_bindings()`
- optional `build_commands()`
- optional `command_aliases`
- optional `build_settings_event_bindings()`
- optional `build_render_scene_overrides(store)`

The registry auto-loads:
- `ui.canvas_features.<name>.manifest`
- fallback: `ui.canvas_features.<name>.widget`

Use this when your feature owns:
- persistent widget state
- feature-specific actions/reducer behavior
- feature property schema for:
  - keyframes
  - settings persistence
  - manual property UI
- toolbar/flyout wiring
- settings events
- render/export payloads used to build the GL scene snapshot

### Command aliases

`CanvasFeatureCommandAlias` allows shared layers to bind to a capability instead of a concrete feature name.

Typical examples:

- `overlay.enabled`
- `overlay.active_state`
- `overlay.active_capture_size`
- `splitter.begin_drag`

Preferred rule:

- shared input/UI/presentation code should use aliases when the capability is generic
- feature-owned code may still use direct `get_canvas_feature_command("<feature>", ...)` calls

## Feature property contract

`CanvasFeatureProperty` lives in `src/ui/canvas_infra/scene/widget_contract.py`.

This is the canonical schema for a canvas feature property.

Each property may describe:
- `id`
- `label`
- `kind`
- `channels`
- `group_id`
- `group_label`
- `setting_key`
- `read_snapshot`
- `write_snapshot`
- optional setting serialization/deserialization

This contract is now the shared source of truth for canvas-specific:
- video editor keyframe tracks
- settings load/save
- manual color/thickness/visibility mutations

If a property can be keyframed and also edited from normal UI, it should not be wired twice by hand. It should be described once as `CanvasFeatureProperty`.

## Viewport contract

Viewport math is not a canvas feature. It is infrastructure.

The current contract lives in:
- `src/ui/canvas_infra/viewport/contract.py`

Use it for shared canvas mechanisms such as:
- display split position mapping
- split-follow-camera logic
- wheel zoom transforms
- pan drag transforms

Do not model zoom as a normal canvas feature.

## GL render contract

Canvas features do not draw directly with PIL, QPainter, or a CPU overlay pipeline.

The render path is:

```
feature apply()
  → runtime_state fields
  → build_render_runtime_context()  [render_context.py]
  → GLRenderRuntimeContext (ctx)
  → CanvasGLRenderPass.paint(widget, ctx)  [canvas_features/*/gl_passes.py]
```

Feature-specific `GLRenderScene` values (visible to the background pass) come from
`WIDGET_FEATURE.build_render_scene_overrides(store)`. The GL scene builder aggregates
these overrides but must not import feature state modules directly.

Simple visual composition belongs in GL shaders:
- split and channel presentation — base shader (`shader_sources/base.py`)
- background diff modes: `highlight`, `grayscale`, `edges` — base shader
- capture ring — `canvas_features/capture/gl_passes.py`
- guides — `canvas_features/guides/gl_passes.py`
- magnifier display + intersection arcs — `canvas_features/magnifier/gl_passes.py`

The current explicit exception is SSIM: the SSIM map is CPU-generated/cached and uploaded
as a texture for GL presentation. This is analysis data generation, not a CPU canvas renderer.

Do not reintroduce:
- `RenderingPipeline`
- PIL/ImageDraw canvas overlays
- QPainter canvas overlays
- CPU fallback workers for static canvas rendering
- GPU failure fallback to CPU rendering for canvas/video snapshots

CPU code may still exist for non-renderer responsibilities such as image decode/load,
crop/resize preparation, analysis map generation, and framebuffer readback.

## How the scene pipeline works

### Build

`src/ui/canvas_infra/scene/builder.py`:
- resolves canvas bounds
- creates `CanvasSceneBuildContext`
- calls every registered `build_primary`
- creates a base `CanvasSceneGraph`
- calls every registered `build_overlay`
- returns the full scene graph

### Apply

`src/ui/canvas_infra/scene/apply.py`:
- creates `CanvasSceneApplyContext`
- calls every registered feature applier

Feature appliers are responsible for populating runtime overlay state on the canvas host.

### Hit-test

`src/ui/canvas_infra/scene/hit_test.py`:
- routes a point through registered hit-testers in pipeline order
- returns the first match

## Source of truth rules

These rules are strict.

### Feature-owned state

If a feature owns runtime or persistent behavior, its state must live in feature-owned storage.

For canvas widget state, prefer:
- `view_state.canvas_widget_state["<feature_name>"]`

Do not keep a second flat compatibility copy in `ViewState`.

Do not keep feature-owned appearance state in `RenderConfig`. `RenderConfig` is for infrastructure/default render configuration, not for per-feature ownership. If a feature needs render or export data, expose a feature command that builds a payload from the feature-owned state.

### No silent fallback writes

Read-only fallback is acceptable in some places.
Write-path fallback is not.

Bad:
- “if active object is missing, update the first object”

Good:
- if active object is missing and a write is requested, fail fast or no-op explicitly

This rule matters especially for multi-instance features such as magnifier.

### Feature geometry belongs to the feature

If geometry exists because a feature exists, put it in the feature folder.

Bad:
- feature-specific bounds helper in `canvas_presentation`

Good:
- `ui/canvas_features/magnifier/bounds.py`

## How to add a new canvas feature

Assume the new feature is called `selection_mask`.

Create:

```text
src/ui/canvas_features/selection_mask/
  __init__.py
  feature.py
  widget.py
  state.py        # optional
  store.py        # optional
  mode.py         # optional
  bounds.py       # optional
  gl_passes.py    # optional — only if the feature needs GL rendering
  workers/        # optional — only for 3+ async compute files
```

### Minimum for a scene-only feature

If the feature only needs scene integration:

1. Create `feature.py`
2. Export `FEATURE: CanvasSceneFeature`
3. Implement:
   - `build_primary`
   - `build_overlay`
   - `apply`
   - optional `hit_test`

That is enough for auto-registration.

### If the feature owns state

If the feature needs reducer behavior or editable properties:

1. Create `widget.py`
2. Export `WIDGET_FEATURE: CanvasWidgetFeature`
3. Implement:
   - `reduce_view_state`
   - `reduce_render_config`
   - optional `build_properties`
   - optional toolbar/settings/render commands

### If the feature exposes user-editable properties

Add `build_properties()` in `widget.py`.

Use `CanvasFeatureProperty` for values such as:
- visibility
- color
- thickness
- enum mode
- default scalar values

If the same value should work in:
- video editor
- settings persistence
- toolbar or flyout actions

then it belongs in `build_properties()`.

Settings keys should be feature namespaced, for example:
- `divider.visible`
- `divider.color`
- `divider.thickness`

Do not introduce flat legacy keys for new feature-owned values.

### If the feature needs persistent widget-owned storage

Add a typed state object in `state.py`, for example:

```python
@dataclass
class SelectionMaskWidgetState:
    enabled: bool = False
```

Then access it through:
- `view_state.canvas_widget_state["selection_mask"]`

Do not add flat compatibility fields to `ViewState` unless the thing is truly global infrastructure.

## When not to use canvas_features

Do not put everything into `ui/canvas_features`.

Use `canvas_infra` when the behavior is foundational for all features:
- zoom
- pan
- split mapping
- generic scene composition

Use `canvas_objects` when the thing is a richer object domain:
- future shapes/annotations if they become document-backed objects

Use `ui/widgets/gl_canvas/shader_sources` only for renderer implementation details. It is not a place for feature policy, persistent state, settings, keyframe schema, or toolbar actions.

## Anti-patterns

Avoid these:

- Adding feature logic to `canvas_infra` because it is convenient.
- Adding new central `if feature == ...` logic.
- Duplicating state in both feature-owned storage and flat `ViewState`.
- Describing the same property once for keyframes and again separately for settings/UI wiring.
- Putting feature geometry helpers into `canvas_presentation`.
- Letting write paths silently fall back to a different instance.
- Treating viewport foundation as a normal editor feature.
- Adding a PIL/QPainter/CPU fallback render path for a GL canvas feature.
- Recreating a central shader facade or monolithic shader module instead of feature-owned `gl_passes.py`.
- Naming infrastructure stack layers after concrete features.
- Importing feature state directly from `ui/widgets/gl_canvas/scene.py` instead of using feature render scene overrides.
- Placing feature shaders under `shader_sources/` instead of in the feature folder.
- Storing shader programs on the widget instead of on the `CanvasGLRenderPass` instance.

## Practical checklist

Before merging a new canvas feature, verify:

- It lives under exactly one feature folder.
- Scene integration is exported via `FEATURE`.
- Reducer/property integration is exported via `WIDGET_FEATURE` if needed.
- User-editable canvas-specific values are declared as `CanvasFeatureProperty`.
- No central registry file was edited to manually add the feature.
- No compatibility bridge was added.
- Feature-specific helpers do not live in `canvas_presentation`.
- Multi-instance behavior does not use silent fallback writes.
- Visual output reaches the renderer through scene/apply contracts, render commands, or explicit `GLRenderScene` overrides.
- No PIL/QPainter/CPU canvas render path was added.
- Shader code lives in `canvas_features/<name>/gl_passes.py` alongside the draw calls that use it.
- Feature-specific `GLRenderScene` fields are supplied by the feature's widget contract.
- Infrastructure z-layers stay generic; feature priority lives in the feature folder.
- No new shader source files were added to `shader_sources/` for this feature.

## Current examples

Good references:

- `src/ui/canvas_features/magnifier/`
  Largest example with scene, state, store, mode, widget integration, and geometry helpers.
- `src/ui/canvas_features/divider/`
  Smaller feature example.
- `src/ui/canvas_features/guides/`
  Overlay feature with owner-state, actions, settings/keyframe properties, and render payload.
- `src/ui/canvas_features/capture/`
  Small owner-state overlay feature with settings/keyframe properties and render payload.
- `src/ui/canvas_infra/viewport/`
  Example of infrastructure that should not be modeled as a consumer feature.

## Short rule of thumb

If you need to explain a new feature as:
- “put the model in one package, the render code in another, reducer changes in a third, and registration in a fourth”

then the feature boundary is wrong.

The intended rule is:
- feature code lives in one feature folder
- infrastructure code lives in `canvas_infra`
- object-domain code lives in `features/canvas_objects`
