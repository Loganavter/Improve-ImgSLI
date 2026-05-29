# Canvas Features Architecture

How canvas-related functionality is organized and how to add new features.

**Core idea**: Each feature operates in its own abstraction layer. It doesn't handle zoom, pan, coordinate transforms, raw Qt events, or serialization — the core infrastructure does. See [Feature Isolation Model](./CONTRACTS.md#feature-isolation-model-the-abstraction) in CONTRACTS.md for why this matters.

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
  resources/
    i18n/              # Translations: auto-discovered and registered at startup
      en/
        {name}.json    # English translations with {name} namespace
      ru/
        {name}.json    # Russian, Portuguese, Chinese — same structure
      pt_BR/
        {name}.json
      zh/
        {name}.json
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

## Gesture Bindings (Mouse Routing)

Shared event code (`src/events/image_label/mouse.py`) must not branch on
feature-specific flags to decide which feature owns a click. Instead each
feature declares its mouse gestures via `WIDGET_FEATURE.build_gesture_bindings`,
and `mouse.py` walks them through `GestureResolver`.

### Contract

```python
from ui.canvas_infra.scene.widget_contract import CanvasFeatureGestureBinding

CanvasFeatureGestureBinding(
    gesture_id="my_feature.do_thing",   # unique, namespaced by feature
    button=Qt.MouseButton.LeftButton.value,
    matches=fn(ctx) -> bool,            # predicate run on press
    is_active=fn(store) -> bool,        # is this gesture currently driving?
    begin=fn(handler, local_pos) | None,
    update=fn(handler, local_pos) | None,
    end=fn(handler) | None,
    owner=str | None,                   # input_session owner id
    priority=int,                       # lower wins; resolver sorts ascending
)
```

The `matches`/`is_active`/`begin`/`update`/`end` callables live inside the
feature package. They are free to call `handler.geometry.*`, `handler.preview.*`,
and `get_canvas_feature_command_by_alias(...)` — but shared event code must
not.

### Rules

1. **No feature literals in `mouse.py`.** No alias name starting with
   `overlay.`, `splitter.`, `magnifier.`, etc. No reads of `view_state.<feature_flag>`
   or `interaction_state.is_dragging_<feature>`. Enforced by
   `tests/contracts/test_events_no_feature_branching.py`.
2. **Predicates gate against app-level workflows.** If the click is part of
   space-bar / preview / single-image-mode handling, the predicate must
   return False so the gesture does not fire (see magnifier's
   `_matches_capture_drag` rejecting space-pressed state).
3. **Fallback gestures use high priority numbers.** Divider's split-drag has
   `priority=1000` so any overlay-style feature can claim the click first.
4. **`begin`/`end` are self-contained.** They wrap the alias call AND any
   `emit_viewport_change`/geometry calls needed to finalize the gesture.
   Shared code never combines them.

### Why This Matters

Before the gesture-binding refactor, `mouse.py` had a central if-tree:
"if overlay enabled and visible → start capture drag, else start split drag."
That looks innocent but:

- Adding a new overlay feature required editing `mouse.py`.
- Hiding all magnifier instances broke divider movement, because
  `is_enabled=True` routed clicks into capture-drag even with nothing visible
  to drag.
- `mouse.py` knew the shape of magnifier's `overlay.active_state` payload
  (`visible_left`/`visible_right`), so any change to that payload silently
  broke routing.

With gesture bindings, `mouse.py` knows nothing about which features exist —
it just asks the resolver.

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
- [ ] Mouse gestures declared via `build_gesture_bindings`, not added to `mouse.py`
- [ ] User-editable values declared as `CanvasFeatureProperty`
- [ ] No central registry file was edited
- [ ] Feature-specific helpers not in `canvas_presentation`
- [ ] Shader code in `gl_passes.py` alongside draw calls
- [ ] No new shader source files under `shader_sources/`

## Working with zoom & pan

A surprising number of bugs in canvas features come from getting zoom and pan
wrong, because there are three coordinate systems in play and several
non-obvious invariants. Read this section before adding any feature that
draws geometry or hit-tests at a specific image position.

### Coordinate systems

| Name | Range | Where it lives |
|---|---|---|
| **Image-px** | `[0, image_w] × [0, image_h]` | Source PIL image, before any scaling. Used by export, hit-test against image content, plugins that read pixel values. |
| **Canvas-px** | `[0, canvas_w] × [0, canvas_h]` | The internal logical render target. **All feature-owned geometry (overlays, magnifier centers, capture rect, guide positions, etc.) must be stored here.** |
| **Widget-px** | `[0, widget.width()] × [0, widget.height()]` | Physical screen coordinates of the GL widget. Used for hit-testing mouse events and for the shader's `TexCoord`. |

Conversions:

- canvas-px → widget-px: applied **once** by the runtime, via a single scale
  `sr = min(widget_w / canvas_w, widget_h / canvas_h)` (preserves aspect,
  letterboxes the rest). Defined in the shared runtime-overlay applicator.
- image-px → canvas-px: handled at upload time; canvas-px is effectively
  image-px after any letterbox compensation. Use the letterbox params from
  `widget.runtime_state._letterbox_params` if you need it.

**If you find yourself computing `sr` by hand inside a feature, you're doing
it wrong.** Store canvas-px, let the runtime convert.

### Where pan and zoom live

There are two separate-but-related concepts:

- **Widget zoom/pan** (`widget.zoom_level`, `widget.pan_offset_x`,
  `widget.pan_offset_y`) — viewport state owned by `GLCanvas`. The shader
  reads these to apply zoom-around-cursor:
  ```glsl
  vec2 uv = (TexCoord - center) / zoom + center - offset;
  ```
- **Store-level split / overlay positions** — semantic positions of overlays
  in canvas-px (`split_position`, magnifier centers, etc.). Stored in the
  Store, persisted across sessions.

These two layers are coordinated by **viewport features** in
`src/ui/canvas_infra/viewport/`. Don't bypass them by reaching into widget
state from your feature.

### The pan-at-zoom-≤1 invariant

**At `zoom <= 1.0`, `pan` must always be `(0, 0)`.**

Rationale: when the image fully fits the widget, "panning" has no meaning —
there's nothing to scroll into view. Allowing non-zero pan at `zoom <= 1.0`
creates desync between the shader (which always uses raw pan) and overlay
formulas (which conventionally treat pan as zero at this zoom). Image moves,
overlays don't, user sees overlays "flying away".

This invariant is enforced **at the source** — `compute_zoom_wheel_transform`
and `compute_zoom_pan_drag_transform` in
`src/ui/canvas_infra/viewport/zoom.py` clamp pan to `(0, 0)` whenever the new
zoom is `≤ 1.0`. Don't add a new place that writes to `pan_offset_x/y`
without respecting this rule.

If you add a feature that:
- Computes its own pan-like transform — clamp pan at the source, same way.
- Reads pan to position an overlay at `zoom <= 1.0` — you can rely on it
  being `0`, no need to gate yourself.
- Reads pan to position an overlay at `zoom > 1.0` — use the raw widget pan,
  do not try to "smooth" or "interpolate" it across the boundary.

### The split-position dual-mode behavior

The split line has two distinct modes:

| Mode | Behavior | Where logic lives |
|---|---|---|
| `zoom > 1.0` (zoomed in) | Line stays **anchored to the camera** — visually pinned to the same widget position. Store `split_position` actively recomputes as zoom/pan changes to keep visual position constant. | `compute_zoom_split_position_for_view_transform` |
| `zoom <= 1.0` (fits / zoomed out) | Line stays **anchored to the image-pixel** — moves with the image as it scales. Store `split_position` stays unchanged. | `compute_zoom_display_split_position` (returns `base` directly, with pan=0 from the invariant above) |

If you add an overlay-style feature with similar "where on the image am I?"
semantics (e.g. magnifier center, crop handles), follow the same pattern:

- Store the canvas-px position in the Store.
- Read widget zoom/pan in your display-time formula.
- Let pan-at-zoom-≤1 invariant do its work — don't second-guess it.

### Runtime cache vs reducible state

State held in the Store splits into two categories:

- **Reducible state** (`Store.viewport`, `Store.document`, `Store.settings`):
  immutable from outside the reducer. Every dispatch creates a new
  `ViewportState`/`DocumentModel`/etc. — fields not explicitly preserved get
  reset to their defaults. **Anything derivable from actions belongs here.**
- **Runtime cache** (`Store.runtime_cache`,
  `src/core/store_runtime_cache.py`): mutable from presenters/renderers. Lives
  outside the reducer pipeline by design. Reducers **cannot** touch it.
  **Anything written as a side effect of rendering belongs here:** texture
  identity hashes (`last_source1_id`, `last_source2_id`), overlay clip rects
  computed during plan-apply, etc.

If you add a field that:
- Comes from a user action / settings / persisted state → reducible state.
- Is written by the GL renderer or presenter after a successful frame →
  `ViewportRuntimeCache`.

Historical pitfall: putting a runtime-cache field into reducible state (e.g.
into `ViewportState.__slots__`) **silently breaks every dispatch** —
`_build_new_viewport_state` creates a fresh `ViewportState` and your field
resets to its default, invalidating the cache on every action. This was the
root cause of a long-standing texture-reupload bug visible only as a subtle
flicker during zoom. Use `ViewportRuntimeCache` and you cannot reproduce this
class of bug.

### Debugging zoom/pan issues

Use the [runtime tracer](./TRACING.md). The minimal-noise category set for
viewport debugging is:

```bash
IMGSLI_TRACE=1 \
IMGSLI_TRACE_KINDS="input.wheel,input.mpress,input.mrel,dispatch.begin,dispatch.end,hit_test,render.apply_plan,store.emit_viewport" \
python src/__main__.py
```

Then `print_tree --top 3` to see the slowest causal chains. Common symptoms
and where to look:

| Symptom | Likely cause | Where to look |
|---|---|---|
| Overlay drifts during zoom-out | Some code wrote pan at `zoom <= 1.0` | `git grep 'pan_offset' src/ui/widgets/gl_canvas/` |
| Overlay flickers / jumps during interaction | Reducer reset a runtime-cache field | Check `_build_new_viewport_state` for missing field carryover; move field to `ViewportRuntimeCache` |
| Mouse hit lands on wrong feature | Hit-test uses widget-px but feature stores widget-px instead of canvas-px | Search for direct `widget.width()` / `widget.height()` in your feature's geometry math |
| Position correct at `zoom = 1` but wrong otherwise | Feature draws using raw store value instead of going through the viewport display formula | Use `compute_display_split_position` / equivalent contract instead of reading store directly in render |

## Examples

- `magnifier/` — largest: scene, state, store, mode, widget, geometry, workers
- `divider/` — small feature
- `guides/` — overlay with owner-state, actions, settings/keyframe properties, render payload
- `capture/` — small overlay with settings/keyframe properties and render payload
- `_template/` — copyable starter template
- `canvas_infra/viewport/` — infrastructure (not a consumer feature)
