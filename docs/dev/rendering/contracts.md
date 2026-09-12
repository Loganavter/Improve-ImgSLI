# Contracts

Field catalog for **interface** canvas contracts. For *why* they exist and how
“contract” is used elsewhere (host call sequences, AST dogmas), start at
[CONTRACTS.md](../CONTRACTS.md#three-senses-of-contract).

## CanvasWidgetFeature (`widget_contract.py`)

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
| `build_gesture_bindings` | Declare mouse gestures the feature claims |
| `build_context_menu_zones` | Declare territory where host context menus are suppressed |
| `build_render_scene_overrides` | Contribute data to the render scene |
| `prepare_worker_viewport` | Prepare viewport state for background workers |
| `apply_plan_runtime_overlay` | Apply overlays from render plan |
| `apply_live_runtime_overlay` | Apply live overlays during rendering |
| `reducer_order` | Sort order for reducer dispatch (default 100) |
| `property_order` | Sort order for property listing (default 100) |

## CanvasSceneFeature (`feature_contract.py`)

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

## CanvasFeatureProperty (`widget_contract.py`)

Canonical schema for a canvas feature property. Describes: `id`, `label`, `kind`, `channels`, `group_id`, `group_label`, `setting_key`, `read_snapshot`, `write_snapshot`, optional serialization.

Shared source of truth for: video editor keyframe tracks, settings load/save, manual color/thickness/visibility mutations. Describe a property once — don't wire it separately for keyframes and settings.

## Command Aliases

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

If the feature is absent, returns `None`. See [CAPABILITY_ALIASES.md](../CAPABILITY_ALIASES.md) for the full discovery/lookup API.

## Canvas Layout Contract

Each feature reports its layout requirement explicitly in normalized
base-image coordinates (see
[The foundation](coordinate-systems.md#the-foundation-normalized-00-10-base-image-space-and-how-uncropcrop-fits-into-it)
for the full geometric model). Shared types live in
`src/shared/rendering/layout_contract.py`: `NormalizedBounds`,
`FeatureLayoutRequirement`, `VirtualCanvasLayout`.

Registration: features register via the `render.layout_requirement` command
alias. Shared builders resolve requirements through `VirtualCanvasLayout` via
`resolve_feature_virtual_layout`. Disabling a feature suppresses its
per-instance animation regardless of stored geometry tracks; core should not
invent additional feature-specific coordinate fixes beyond this contract.

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

### Runtime cache vs reducible state
- anything derived from actions lives in reducible state
- anything written as a side effect of a successful frame lives in the runtime cache, outside the reducer pipeline
- matters for QRhi resource-readiness flags the same way it matters for any other derived-vs-cached value
