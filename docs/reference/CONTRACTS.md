# Application Contracts

Complete list of all contracts, protocols, and interfaces used throughout the application.

## Canvas Feature Contracts

### CanvasWidgetFeature
Presentation-layer contract for canvas-integrated widgets. Owns reducers, commands, properties, toolbar bindings, and settings integration.

**Location**: `src/ui/canvas_infra/scene/widget_contract.py`

**Key methods**:
- `reduce_view_state()` — handle view state actions
- `reduce_render_config()` — handle render config actions
- `reduce_interaction_state()` — (optional) handle interaction actions
- `build_commands()` — register callable commands
- `build_properties()` — register keyframe-animatable properties
- `build_toolbar_bindings()` — connect toolbar controls
- `build_state_queries()` — register state read interface
- `build_state_commands()` — register state write interface

### CanvasFeatureProperty
Canonical schema for a feature property. Describes: `id`, `label`, `kind`, `channels`, `group_id`, `read_snapshot`, `write_snapshot`.

**Location**: `src/ui/canvas_infra/scene/widget_contract.py`

**Use case**: Shared source of truth for video editor keyframe tracks, settings load/save, and manual color/thickness/visibility mutations.

### CanvasFeatureStateQuery
Query interface for reading feature state directly.

**Fields**: `query_id`, `handler`

**Example**: `query_feature_state(store, "magnifier", "active_state")`

### CanvasFeatureStateCommand
Command interface for modifying feature state.

**Fields**: `command_id`, `handler`

**Example**: `execute_feature_command(store, "magnifier", "set_active_size", 0.5)`

### CanvasFeatureToolbarBinding
Connects toolbar controls to feature commands.

**Fields**: `control_id`, `on_toggled`, `on_value_changed`, `on_right_clicked`, `on_middle_clicked`, `on_pressed`, `on_released`, `sync_state`

### CanvasFeatureCommandAlias
Maps feature-agnostic capability names to feature-specific commands.

**Example**: `"magnifier.add_instance"` → maps to `magnifier` feature's `add_instance` command

### CanvasSceneFeature
Scene-graph contract. Only needed if feature participates in hit-testing, stacking, or scene-level apply.

**Location**: `src/ui/canvas_infra/scene/feature_contract.py`

**Key methods**:
- `build_primary()` — create primary scene objects
- `build_overlay()` — create overlay scene objects
- `apply()` — apply scene state to viewport
- `hit_test()` — (optional) find object at position

### CanvasFeatureZOrder
Z-ordering specification for scene objects.

**Fields**: `stack_role`, `layer`, `priority`, `always_on_top`, `always_on_bottom`, `active_bias`, `selectable_when_hidden`, `tags`

### CanvasGLRenderPass
GL render pass contract for feature-owned drawing.

**Location**: `src/ui/canvas_infra/scene/gl_pass_contract.py`

**Key methods**:
- `initialize()` — setup GL resources
- `should_paint()` — check if pass has anything to draw
- `paint()` — issue draw calls
- `cleanup()` — release GL resources

**Properties**: `stack_role`, `visibility`

### SceneVisibility
Enum flag controlling when a GL pass is active.

**Values**: `INTERACTIVE`, `EXPORT`, `PREVIEW`, `ALL`

### RenderPhase (aka CanvasGLLayer)
Ordered render phases for GL passes.

**Values**:
- `BASE_IMAGE` (0)
- `IMAGE_DECORATION` (10)
- `IMAGE_ANNOTATION` (20)
- `VIEW_ANNOTATION` (30)
- `HUD` (40)
- `DEBUG` (50)

## Viewport & Interaction Contracts

### DisplaySplitPositionRequest
Request object for computing split line position in display coordinates.

**Fields**: `widget_width`, `widget_height`, `image_width`, `image_height`, `split_visual`, `is_horizontal`, `zoom_level`, `pan_offset_x`, `pan_offset_y`, `content_rect`

### SplitPositionForViewTransformRequest
Request for computing split position after view transform.

**Fields**: Similar to DisplaySplitPositionRequest, plus `new_zoom`, `new_pan_x`, `new_pan_y`

### WheelZoomRequest
Wheel zoom action parameters.

**Fields**: `widget_width`, `widget_height`, `mouse_x`, `mouse_y`, `current_zoom`, `current_pan_x`, `current_pan_y`, `angle_delta_y`

### PanDragRequest
Pan drag action parameters.

**Fields**: `widget_width`, `widget_height`, `current_zoom`, `current_pan_x`, `current_pan_y`, `last_mouse_x`, `last_mouse_y`, `mouse_x`, `mouse_y`

### OverlayMovementHandler
Protocol for objects that handle overlay geometry manipulation.

**Location**: `src/core/interaction_protocols.py`

**Methods**:
- `get_offset()` → position offset
- `get_spacing()` → spacing between parts
- `get_internal_split()` → internal split ratio
- `has_both_sides()` → whether both sides visible
- `set_offset(offset)` — update position
- `set_spacing(spacing)` — update spacing
- `get_spacing_limits()` → (min, max) tuple
- `emit_combined_state()` — notify state change

## Layout Contracts

### NormalizedBounds
Normalized geometry bounds in 0..1 space (may extend outside for magnifiers).

**Fields**: `x_min`, `x_max`, `y_min`, `y_max`

**Methods**: `unit()`, `width`, `height`, `union(other)`

### FeatureLayoutRequirement
Feature's layout requirement specification.

**Fields**: `feature_id`, `bounds` (NormalizedBounds)

### VirtualCanvasLayout
Resolved union of base content and all feature requirements.

**Fields**: `canvas_bounds`, `content_bounds`

**Methods**: `pad_left_units`, `pad_right_units`, `pad_top_units`, `pad_bottom_units`, `resolve_padding_pixels()`

## Canvas Widget Protocols

### BaseCanvasProtocol
Base protocol for all canvas widgets.

**Location**: `src/ui/widgets/gl_canvas/contracts.py`

**Signals**: `firstFrameRendered`, `firstVisualFrameReady`, `zoomChanged`, `mousePressed`, `mouseMoved`, `mouseReleased`, `wheelScrolled`, `keyPressed`, `keyReleased`

**Properties**: `zoom_level`, `pan_offset_x`, `pan_offset_y`, `split_position`, `is_horizontal`

**Methods**: `set_store()`, `set_render_scene()`, `set_split_position_sync()`, `set_layers()`, `set_feature_overlay_gpu_params()`, `clear()`, etc.

### GlLikeCanvasProtocol
GL canvas protocol extending BaseCanvasProtocol.

**Additional methods**: `set_pil_layers()`

### ExportCanvasProtocol
Export/offscreen canvas protocol extending BaseCanvasProtocol.

**Additional methods**: `configure_offscreen_render()`, `grabFramebuffer()`

## Tab System Contract

### TabContract
Base interface for workspace tabs.

**Location**: `src/tabs/contract.py`

**Properties**: `session_type`, `display_name`, `icon`, `resources_dir`, `i18n_namespace`

**Methods**:
- `create_page()` — create tab widget
- `on_activated()` — tab becoming active
- `on_deactivated()` — tab becoming inactive
- `accepts_drop()` — can handle files
- `handle_drop()` — process dropped files
- `on_session_created()` — new session created
- `on_session_closed()` — session closed

## Core Event Contract

### Event
Base protocol for all events.

**Location**: `src/core/events.py`

**Usage**: Publisher → EventBus → Subscribers pattern

---

## Summary by Category

| Category | Count | Files |
|----------|-------|-------|
| Canvas Features | 11 | `widget_contract.py`, `feature_contract.py`, `gl_pass_contract.py` |
| Viewport/Interaction | 5 | `viewport/contract.py`, `interaction_protocols.py` |
| Layout | 3 | `shared/rendering/layout_contract.py` |
| Canvas Widgets | 3 | `gl_canvas/contracts.py` |
| Tab System | 1 | `tabs/contract.py` |
| Core | 1 | `events.py` |
| **Total** | **24** | |
