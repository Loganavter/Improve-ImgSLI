# Canvas Feature Guide

How to add a new canvas feature to ImgSLI.

## Quick Start

1. Copy `src/ui/canvas_features/_template/` to `src/ui/canvas_features/<your_feature>/`
2. Rename `_template` to your feature name in `widget.py` (`name=` field)
3. Add your logic
4. Done — all registries auto-discover it

No central files need editing. Packages starting with `_` are excluded from auto-discovery.

## Package Structure

```
src/ui/canvas_features/<name>/
  __init__.py
  manifest.py          # REQUIRED: exports WIDGET_FEATURE and/or FEATURE
  widget.py            # CanvasWidgetFeature definition
  feature.py           # CanvasSceneFeature definition (if scene-participating)
  gl_passes.py         # GL_RENDER_PASSES list (if rendering)
  state.py             # Feature-local state helpers
  commands.py          # Command handlers
  ...                  # Any other feature-owned modules
```

## What Gets Auto-Discovered

| Registry | Looks for | In module |
|---|---|---|
| `widget_registry` | `WIDGET_FEATURE: CanvasWidgetFeature` | `manifest.py` or `widget.py` |
| `feature_registry` | `FEATURE: CanvasSceneFeature` | `manifest.py` or `feature.py` |
| `gl_pass_registry` | `GL_RENDER_PASSES: list[CanvasGLRenderPass]` | `gl_passes.py` |

## Contracts

### CanvasWidgetFeature (widget_contract.py)

The presentation-layer contract. Required fields:

| Field | Type | Required | Purpose |
|---|---|---|---|
| `name` | `str` | yes | Unique feature identifier |
| `reduce_view_state` | `fn(ViewState, Action) -> ViewState` | yes | Handle actions that change view state |
| `reduce_render_config` | `fn(RenderConfig, Action) -> RenderConfig` | yes | Handle actions that change render config |

Optional fields:

| Field | Purpose |
|---|---|
| `reduce_interaction_state` | Handle interaction-related actions |
| `reduce_geometry_state` | Handle geometry-related actions |
| `build_commands` | `fn() -> dict[str, handler]` — register callable commands |
| `command_aliases` | `tuple[CanvasFeatureCommandAlias, ...]` — expose commands as capability aliases |
| `build_properties` | Register keyframe-animatable properties |
| `build_toolbar_bindings` | Connect toolbar controls |
| `build_settings_event_bindings` | React to settings dialog events |
| `build_render_scene_overrides` | Contribute data to the GL render scene |
| `prepare_worker_viewport` | Prepare viewport state for background workers |
| `apply_plan_runtime_overlay` | Apply overlays from render plan |
| `apply_live_runtime_overlay` | Apply live overlays during rendering |
| `reducer_order` | Sort order for reducer dispatch (default 100) |
| `property_order` | Sort order for property listing (default 100) |

### CanvasSceneFeature (feature_contract.py)

The scene-graph contract. Only needed if your feature participates in the scene graph (has objects that need hit-testing, stacking, or scene-level apply).

| Field | Type | Required | Purpose |
|---|---|---|---|
| `name` | `str` | yes | Must match widget feature name |
| `build_primary` | `fn(ctx) -> tuple[SceneObject, ...]` | yes | Create scene objects |
| `build_overlay` | `fn(graph, ctx) -> tuple[SceneObject, ...]` | yes | Create overlay objects after primaries |
| `apply` | `fn(graph, ctx) -> None` | yes | Apply scene state to viewport |
| `hit_test` | `fn(graph, point) -> SceneObject\|None` | no | Find object at position |
| `z_order` | `CanvasFeatureZOrder` | no | Stacking role (use `stack_role=CanvasStackRole.X`) |

### CanvasGLRenderPass (gl_pass_contract.py)

A GL render pass. Set `stack_role` — never hardcode `layer`/`priority`.

```python
from ui.canvas_infra.scene.gl_pass_contract import CanvasGLRenderPass
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole

class MyPass(CanvasGLRenderPass):
    stack_role = CanvasStackRole.VIEW_ANNOTATION  # central policy resolves order

    def initialize(self, widget) -> None: ...
    def should_paint(self, ctx) -> bool: ...
    def paint(self, widget, ctx) -> None: ...
    def cleanup(self, widget) -> None: ...
```

Available roles (defined in `stacking_policy.py`):

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

If the feature is absent, `get_canvas_feature_command_by_alias` returns `None`.

## Checklist

- [ ] Package in `src/ui/canvas_features/<name>/`
- [ ] `manifest.py` exports `WIDGET_FEATURE` (and optionally `FEATURE`)
- [ ] `name` field is unique and does not start with `_`
- [ ] Reducers are no-op if feature has no state actions
- [ ] Commands exposed via aliases (not direct feature-name lookups)
- [ ] GL passes use `stack_role`, not hardcoded `layer`/`priority`
- [ ] Scene z_order uses `stack_role` via `CanvasFeatureZOrder`
- [ ] No imports of this feature in shared `ui/`, `events/`, or `plugins/` code
