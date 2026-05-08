# Canvas Features Architecture

This document describes how canvas-related functionality is organized in the project and how to add new features without scattering code across unrelated layers.

## Goals

- One clear home for each canvas feature.
- No legacy bridges or shadow sources of truth.
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
- `src/features/canvas_objects/<object_name>/`

This is for document-backed, richer object types that are more than overlays. Example:
- `text`

Use this area when the thing has heavier object semantics: layout, editing, selection, serialization, richer keyframing behavior, and not just an overlay pass.

## Current directory model

### Canvas infra

- `src/ui/canvas_infra/scene/feature_contract.py`
  Defines `CanvasSceneFeature`.
- `src/ui/canvas_infra/scene/widget_contract.py`
  Defines `CanvasWidgetFeature` and `CanvasFeatureProperty`.
- `src/ui/canvas_infra/scene/feature_registry.py`
  Auto-discovers `ui.canvas_features.*.feature`.
- `src/ui/canvas_infra/scene/widget_registry.py`
  Auto-discovers `ui.canvas_features.*.widget`.
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

- `feature.py`
  Scene build/apply/hit-test integration.
- `widget.py`
  Reducer and property schema contributions.
- `state.py`
  Feature-owned persistent widget state.
- `store.py`
  Feature-owned store/service helpers.
- `mode.py`
  Feature policy rules.
- `bounds.py`
  Feature-specific geometry helpers.

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

## Contracts

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
- `ui.canvas_features.<name>.feature`

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
- optional `build_settings_event_bindings()`
- optional `build_render_scene_overrides(store)`

The registry auto-loads:
- `ui.canvas_features.<name>.widget`

Use this when your feature owns:
- persistent widget state
- feature-specific actions/reducer behavior
- feature property schema for:
  - keyframes
  - settings persistence
  - manual property UI
- toolbar/flyout wiring
- settings events
- render/export payloads

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

Do not keep feature-owned appearance state in `RenderConfig`. `RenderConfig` is for infrastructure/default render configuration, not for per-feature ownership. If a feature needs export or CPU-render data, expose a feature command that builds a render payload from the feature-owned state.

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

Use `features/canvas_objects` when the thing is a richer object domain:
- text
- future shapes/annotations if they become document-backed objects

## Anti-patterns

Avoid these:

- Adding feature logic to `canvas_infra` because it is convenient.
- Adding new central `if feature == ...` logic.
- Duplicating state in both feature-owned storage and flat `ViewState`.
- Describing the same property once for keyframes and again separately for settings/UI wiring.
- Putting feature geometry helpers into `canvas_presentation`.
- Letting write paths silently fall back to a different instance.
- Treating viewport foundation as a normal editor feature.

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
