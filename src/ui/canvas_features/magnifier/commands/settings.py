from __future__ import annotations

from ..actions import (
    SetMagnifierMovementInterpolationMethodAction,
    SetOptimizeMagnifierMovementAction,
)
from ..state import get_magnifier_widget_state

def settings_set_optimize_movement(store, enabled: bool) -> bool:
    if store is None or getattr(store, "viewport", None) is None:
        return False
    enabled = bool(enabled)
    if store.viewport.view_state.optimize_interactive_movement == enabled:
        return False
    store.get_dispatcher().dispatch(
        SetOptimizeMagnifierMovementAction(enabled),
        scope="viewport",
    )
    if hasattr(store, "invalidate_render_cache"):
        store.invalidate_render_cache()
    if hasattr(store, "emit_viewport_change"):
        store.emit_viewport_change()
    return True

def settings_set_movement_interpolation(store, method: str) -> bool:
    if store is None or getattr(store, "viewport", None) is None:
        return False
    method = str(method)
    current = store.viewport.render_config.interactive_movement_interpolation_method
    if current == method:
        return False
    store.get_dispatcher().dispatch(
        SetMagnifierMovementInterpolationMethodAction(method),
        scope="viewport",
    )
    if hasattr(store, "invalidate_render_cache"):
        store.invalidate_render_cache()
    if hasattr(store, "emit_viewport_change"):
        store.emit_viewport_change()
    return True

def settings_apply_behavior(store, behavior: dict) -> dict:
    state = get_magnifier_widget_state(store.viewport.view_state)
    changes = {}
    if "intersection_highlight_enabled" in behavior:
        new_val = bool(behavior["intersection_highlight_enabled"])
        if new_val != state.intersection_highlight_enabled:
            state.intersection_highlight_enabled = new_val
            changes["intersection_highlight_enabled"] = new_val
    if "auto_color_new_instances" in behavior:
        new_val = bool(behavior["auto_color_new_instances"])
        if new_val != state.auto_color_new_instances:
            state.auto_color_new_instances = new_val
            changes["auto_color_new_instances"] = new_val
    return changes

def settings_initialize(store, get_setting) -> None:
    from ..constants import (
        DEFAULT_CAPTURE_POS_RELATIVE,
        DEFAULT_MAGNIFIER_OFFSET_RELATIVE,
        DEFAULT_MAGNIFIER_SPACING_RELATIVE,
    )
    from ..store import (
        MagnifierStoreService,
        default_capture_size,
        default_magnifier_size,
        set_default_capture_size,
        set_default_magnifier_size,
    )

    view = store.viewport.view_state
    set_default_magnifier_size(
        view, get_setting("magnifier_size_relative", 0.4, float)
    )
    set_default_capture_size(
        view, get_setting("capture_size_relative", 0.1, float)
    )
    initial_spacing = get_setting(
        "magnifier_spacing_relative", DEFAULT_MAGNIFIER_SPACING_RELATIVE, float
    )

    scene_state = MagnifierStoreService(store)
    default_magnifier = scene_state.ensure_active_magnifier(create_if_missing=False)
    if default_magnifier is not None:
        scene_state.move_object_source_position(
            default_magnifier.id, DEFAULT_CAPTURE_POS_RELATIVE
        )
        scene_state.set_active_magnifier_offset(DEFAULT_MAGNIFIER_OFFSET_RELATIVE)
        scene_state.set_active_magnifier_spacing(initial_spacing)
        scene_state.set_active_magnifier_size(default_magnifier_size(view))
        scene_state.set_active_capture_size(default_capture_size(view))

def settings_persist(store, save_setting) -> None:
    from ..constants import DEFAULT_MAGNIFIER_SPACING_RELATIVE
    from ..store import (
        MagnifierStoreService,
        default_capture_size,
        default_magnifier_size,
    )

    view = store.viewport.view_state
    scene_state = MagnifierStoreService(store)
    active_magnifier = scene_state.get_active_or_first_magnifier()
    save_setting(
        "magnifier_size_relative",
        active_magnifier.size_relative
        if active_magnifier is not None
        else default_magnifier_size(view),
    )
    save_setting(
        "capture_size_relative",
        active_magnifier.capture_size_relative
        if active_magnifier is not None
        else default_capture_size(view),
    )
    save_setting(
        "magnifier_spacing_relative",
        active_magnifier.spacing_relative
        if active_magnifier is not None
        else DEFAULT_MAGNIFIER_SPACING_RELATIVE,
    )
