from __future__ import annotations

from .gl_overlay import apply_magnifier_gl_overlay
from .plan_overlay import apply_magnifier_plan_overlay
from .properties import build_magnifier_properties
from .reducers import (
    reduce_magnifier_cache_state,
    reduce_magnifier_geometry_state,
    reduce_magnifier_interaction_state,
    reduce_magnifier_render_config,
    reduce_magnifier_view_state,
)
from .runtime_hooks import (
    build_magnifier_render_scene_overrides,
    command_build_render_canvas_payload,
    prepare_magnifier_worker_viewport,
)
from .settings_bindings import build_magnifier_settings_event_bindings
from .toolbar.bindings import build_magnifier_toolbar_bindings
from .commands import build_magnifier_commands as assemble_magnifier_commands
from ui.canvas_infra.scene.widget_contract import (
    CanvasFeatureCommandAlias,
    CanvasWidgetFeature,
)

def build_magnifier_commands():
    return assemble_magnifier_commands(command_build_render_canvas_payload)

MAGNIFIER_COMMAND_ALIASES = (
    CanvasFeatureCommandAlias("overlay.enabled", "query.enabled"),
    CanvasFeatureCommandAlias("overlay.is_horizontal", "query.is_horizontal"),
    CanvasFeatureCommandAlias("overlay.active_state", "query.active_state"),
    CanvasFeatureCommandAlias("overlay.all_states", "query.all_states"),
    CanvasFeatureCommandAlias("overlay.behavior_settings", "query.behavior_settings"),
    CanvasFeatureCommandAlias("overlay.active_combined", "query.active_combined"),
    CanvasFeatureCommandAlias("overlay.active_divider_color", "query.active_divider_color"),
    CanvasFeatureCommandAlias("overlay.active_divider_visible", "query.active_divider_visible"),
    CanvasFeatureCommandAlias("overlay.active_divider_thickness", "query.active_divider_thickness"),
    CanvasFeatureCommandAlias("overlay.active_border_color", "query.active_border_color"),
    CanvasFeatureCommandAlias("overlay.active_capture_size", "query.active_capture_size"),
    CanvasFeatureCommandAlias("overlay.total_count", "query.total_count"),
    CanvasFeatureCommandAlias("overlay.movement_handler", "query.movement_handler"),
    CanvasFeatureCommandAlias("overlay.canvas_payload", "render.canvas_payload"),
    CanvasFeatureCommandAlias("overlay.render_drawing_coords", "render.drawing_coords"),
    CanvasFeatureCommandAlias("overlay.render_compute_padding", "render.compute_padding"),
    CanvasFeatureCommandAlias("overlay.render_build_layout", "render.build_layout"),
    CanvasFeatureCommandAlias("overlay.render_shift_layout_to_tile", "render.shift_layout_to_tile"),
    CanvasFeatureCommandAlias("overlay.snapshot_normalize", "snapshot.normalize_store"),
    CanvasFeatureCommandAlias(
        "overlay.snapshot_retarget_to_padded_canvas",
        "snapshot.retarget_to_padded_canvas",
    ),
    CanvasFeatureCommandAlias("overlay.settings_initialize", "settings.initialize"),
    CanvasFeatureCommandAlias("overlay.settings.persist", "settings.persist"),
    CanvasFeatureCommandAlias("overlay.toggle_enabled", "viewport.toggle_enabled"),
    CanvasFeatureCommandAlias("overlay.set_active_size", "viewport.set_active_size"),
    CanvasFeatureCommandAlias("overlay.set_active_instance", "viewport.set_active_instance"),
    CanvasFeatureCommandAlias("overlay.set_active_capture_size", "viewport.set_active_capture_size"),
    CanvasFeatureCommandAlias(
        "overlay.set_active_visibility_parts",
        "viewport.set_active_visibility_parts",
    ),
    CanvasFeatureCommandAlias("overlay.set_active_orientation", "viewport.set_active_orientation"),
    CanvasFeatureCommandAlias("overlay.move_active_position", "viewport.move_active_position"),
    CanvasFeatureCommandAlias("overlay.should_show_panel", "query.should_show_panel"),
    CanvasFeatureCommandAlias("overlay.add_instance", "viewport.add_instance"),
    CanvasFeatureCommandAlias("overlay.remove_active_instance", "viewport.remove_active_instance"),
    CanvasFeatureCommandAlias(
        "overlay.set_instance_visibility",
        "viewport.set_instance_visibility",
    ),
    CanvasFeatureCommandAlias("overlay.set_internal_split", "viewport.set_internal_split"),
    CanvasFeatureCommandAlias("overlay.set_all_freeze", "viewport.set_all_freeze"),
    CanvasFeatureCommandAlias("overlay.set_active_freeze", "viewport.set_active_freeze"),
    CanvasFeatureCommandAlias("overlay.set_active_combined", "viewport.set_active_combined"),
    CanvasFeatureCommandAlias("overlay.set_active_border_color", "viewport.set_active_border_color"),
    CanvasFeatureCommandAlias("overlay.set_active_divider_color", "viewport.set_active_divider_color"),
    CanvasFeatureCommandAlias("overlay.set_active_laser_enabled", "viewport.set_active_laser_enabled"),
    CanvasFeatureCommandAlias("overlay.begin_capture_drag", "interaction.begin_capture_drag"),
    CanvasFeatureCommandAlias("overlay.update_capture_drag", "interaction.update_capture_drag"),
    CanvasFeatureCommandAlias("overlay.end_capture_drag", "interaction.end_capture_drag"),
    CanvasFeatureCommandAlias("overlay.begin_internal_split_drag", "interaction.begin_internal_split_drag"),
    CanvasFeatureCommandAlias("overlay.update_internal_split_drag", "interaction.update_internal_split_drag"),
    CanvasFeatureCommandAlias("overlay.end_internal_split_drag", "interaction.end_internal_split_drag"),
    CanvasFeatureCommandAlias("overlay.preview_begin", "interaction.preview_begin"),
    CanvasFeatureCommandAlias("overlay.preview_restore", "interaction.preview_restore"),
    CanvasFeatureCommandAlias("overlay.preview_set_side", "interaction.preview_set_side"),
    CanvasFeatureCommandAlias("overlay.emit_changed", "interaction.emit_overlay_changed"),
    CanvasFeatureCommandAlias("overlay.rebuild", "runtime.rebuild_overlay"),
    CanvasFeatureCommandAlias("overlay.render_layer", "runtime.render_layer"),
    CanvasFeatureCommandAlias("overlay.stop_interactive_movement", "runtime.stop_interactive_movement"),
    CanvasFeatureCommandAlias("overlay.update_capture_area_display", "runtime.update_capture_area_display"),
    CanvasFeatureCommandAlias("overlay.request_cached_diff", "runtime.request_cached_diff_image"),
    CanvasFeatureCommandAlias("overlay.settings.apply_behavior", "settings.apply_behavior"),
    CanvasFeatureCommandAlias("overlay.settings.toggle_divider_visibility", "settings.toggle_divider_visibility"),
    CanvasFeatureCommandAlias("overlay.settings.set_divider_color", "settings.set_divider_color"),
    CanvasFeatureCommandAlias("overlay.settings.set_divider_thickness", "settings.set_divider_thickness"),
    CanvasFeatureCommandAlias("overlay.settings.set_border_color", "settings.set_border_color"),
)

def build_widget_feature() -> CanvasWidgetFeature:
    return CanvasWidgetFeature(
        name="magnifier",
        reduce_view_state=reduce_magnifier_view_state,
        reduce_render_config=reduce_magnifier_render_config,
        reduce_interaction_state=reduce_magnifier_interaction_state,
        reduce_geometry_state=reduce_magnifier_geometry_state,
        reduce_cache_state=reduce_magnifier_cache_state,
        build_properties=build_magnifier_properties,
        build_toolbar_bindings=build_magnifier_toolbar_bindings,
        build_commands=build_magnifier_commands,
        command_aliases=MAGNIFIER_COMMAND_ALIASES,
        build_settings_event_bindings=build_magnifier_settings_event_bindings,
        build_render_scene_overrides=build_magnifier_render_scene_overrides,
        prepare_worker_viewport=prepare_magnifier_worker_viewport,
        apply_plan_runtime_overlay=apply_magnifier_plan_overlay,
        apply_live_runtime_overlay=apply_magnifier_gl_overlay,
        i18n_namespace="features.magnifier",
        reducer_order=50,
        property_order=50,
    )

WIDGET_FEATURE = build_widget_feature()
