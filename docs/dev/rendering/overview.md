# Overview

The render backend is QRhi. This documentation states the target model the
architecture should guarantee, not necessarily a line-by-line audit of every
current file — see [Doc status](#doc-status) at the end.

**Core idea**: a feature doesn't handle zoom, pan, coordinate transforms, raw
Qt events, or serialization — the infrastructure does. See
[Feature Isolation Model](../CONTRACTS.md#feature-isolation-model-the-abstraction).

## Quick Start

1. Copy `src/tabs/image_compare/canvas/features/_template/` to
   `src/tabs/image_compare/canvas/features/<your_feature>/`
2. Rename `_template` to your feature name in `widget.py` (`name=` field)
3. Add your logic
4. Done — all registries auto-discover it

No central files need editing. Packages starting with `_` are excluded from
auto-discovery.

## Top-level Split

### 1. Canvas infrastructure (`src/ui/canvas_infra/`)

The framework layer. Owns scene contracts, feature registries, scene
builder/composer, apply pipeline, hit-test routing, viewport contracts,
zoom/pan/split state and math, render-pass scene contracts. Does not own
feature business logic. Shared across every tab — not tab-owned (see
[Package Structure](package-structure.md) below).

Key files:
- `scene/feature_contract.py` — `CanvasSceneFeature`
- `scene/widget_contract.py` — `CanvasWidgetFeature`, `CanvasFeatureProperty`
- `scene/feature_registry.py` — auto-discovers `manifest.py`, fallback `feature.py`
- `scene/widget_registry.py` — auto-discovers `manifest.py`, fallback `widget.py`
- `scene/pass_contract.py` — `CanvasRenderPass`, `SceneVisibility`, single-preview helpers
- `scene/property_access.py` — shared property read/write/persistence
- `scene/pipeline.py` — ordered build/apply/hit-test pipelines
- `scene/builder.py` — builds `CanvasSceneGraph`
- `scene/apply.py` — applies built scene to canvas runtime
- `scene/hit_test.py` — routes hit-testing through registered features
- `scene/stacking_policy.py` — `CanvasStackRole`, central ordering tables
- `viewport/contract.py` — viewport feature contract
- `viewport/state.py` — viewport runtime state accessors
- `viewport/zoom.py` — zoom/pan/split implementation

### 2. Canvas features (`src/tabs/<tab>/canvas/features/<name>/`)

Editor-facing canvas features (magnifier, divider, guides, capture,
filename_overlay). Each keeps its scene logic, state logic, and
widget/reducer integration in its own folder, owned by the tab that
registers the feature package (currently `image_compare` and `multi_compare`).

### 3. Canvas presentation (`src/ui/canvas_presentation/`)

Not a feature home. Used for live store snapshots, render/export-facing
store transformation, canvas surface integration. Feature-specific helpers
should not live here.

### 4. QRhi canvas renderer (`src/tabs/image_compare/canvas/`, backend bits under `src/ui/widgets/canvas/`)

Renderer backend, not a feature home. Owns QRhi resource setup, buffer/texture
upload/readback, renderer-facing consumption of the render scene/runtime
context, base canvas shader source, feature render-pass discovery and
dispatch loop.

Shader ownership:
- `shader_sources/base.py` — main canvas background, split/channel/diff modes
- `shader_sources/common.py` — shared shader prolog helpers only
- Feature shaders live inside `canvas/features/<name>/` (`passes.py`,
  `shaders.py`, or `shaders/`), not in the generic canvas renderer.

## Examples

- `magnifier/` — largest: scene, state, store, mode, widget, geometry, workers
- `divider/` — small feature
- `guides/` — overlay with owner-state, actions, settings/keyframe properties, render payload
- `capture/` — small overlay with settings/keyframe properties and render payload
- `_template/` — copyable starter template
- `canvas_infra/viewport/` — infrastructure (not a consumer feature)

## Doc status

This documentation states the target model. It does not claim the current
codebase fully complies with it in every corner — most notably, whether every
base-image-anchored pass correctly treats viewport-formula output as final,
and whether every pipeline sets its alpha blend factors explicitly rather
than relying on defaults (see [render-pass-contract.md](render-pass-contract.md)).
A line-by-line audit against this documentation is a separate, ongoing task.
