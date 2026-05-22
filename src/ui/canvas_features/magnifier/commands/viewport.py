from __future__ import annotations

from typing import Any

from domain.types import Point

def viewport_toggle_enabled(store, enabled: bool):
    from ..mode import MagnifierModeService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    return MagnifierModeService(store).toggle_from_button(bool(enabled))

def viewport_ensure_active(store):
    from ..store import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    return MagnifierStoreService(store).ensure_active_magnifier()

def viewport_set_active_size(store, size: float):
    from ..store import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    result = MagnifierStoreService(store).set_active_magnifier_size(float(size))
    store.emit_viewport_change()
    return result

def viewport_set_active_capture_size(store, size: float):
    from ..store import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    result = MagnifierStoreService(store).set_active_capture_size(float(size))
    store.emit_viewport_change()
    return result

def viewport_set_active_offset(store, offset):
    from ..store import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    result = MagnifierStoreService(store).set_active_magnifier_offset(offset)
    store.emit_viewport_change()
    return result

def viewport_set_active_spacing(store, spacing: float):
    from ..store import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    result = MagnifierStoreService(store).set_active_magnifier_spacing(float(spacing))
    store.emit_viewport_change()
    return result

def viewport_set_active_border_color(store, color):
    from ..store import MagnifierStoreService, update_magnifier_model

    if store is None or getattr(store, "viewport", None) is None:
        return None
    scene_state = MagnifierStoreService(store)
    model = scene_state.get_active_or_first_magnifier()
    if model is None:
        return None
    result = update_magnifier_model(
        store.viewport.view_state,
        store.viewport.render_config,
        model.id,
        border_color=color,
    )
    store.emit_viewport_change()
    return result

def viewport_set_active_divider_color(store, color):
    from ..store import MagnifierStoreService, update_magnifier_model

    if store is None or getattr(store, "viewport", None) is None:
        return None
    scene_state = MagnifierStoreService(store)
    model = scene_state.get_active_or_first_magnifier()
    if model is None:
        return None
    result = update_magnifier_model(
        store.viewport.view_state,
        store.viewport.render_config,
        model.id,
        divider_color=color,
    )
    store.emit_viewport_change()
    return result

def viewport_set_active_laser_enabled(store, enabled: bool):
    from ..store import MagnifierStoreService, update_magnifier_model

    if store is None or getattr(store, "viewport", None) is None:
        return None
    scene_state = MagnifierStoreService(store)
    model = scene_state.get_active_or_first_magnifier()
    if model is None:
        return None
    result = update_magnifier_model(
        store.viewport.view_state,
        store.viewport.render_config,
        model.id,
        show_laser=bool(enabled),
    )
    store.emit_viewport_change()
    return result

def viewport_set_active_visibility_parts(
    store,
    *,
    left: bool | None = None,
    center: bool | None = None,
    right: bool | None = None,
):
    from ..store import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    result = MagnifierStoreService(store).set_active_magnifier_visibility_parts(
        left=left,
        center=center,
        right=right,
    )
    store.emit_viewport_change()
    return result

def viewport_set_active_orientation(store, is_horizontal: bool):
    from ..store import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    result = MagnifierStoreService(store).set_active_magnifier_orientation(
        bool(is_horizontal)
    )
    store.emit_viewport_change()
    return result

def viewport_move_active_position(store, position):
    from ..store import MagnifierStoreService, active_magnifier_id

    if store is None or getattr(store, "viewport", None) is None:
        return None
    result = MagnifierStoreService(store).move_object_source_position(
        active_magnifier_id(store.viewport.view_state),
        position,
    )
    store.emit_viewport_change()
    return result

def viewport_set_internal_split(store, location):
    from ..store import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    scene_state = MagnifierStoreService(store)
    model = scene_state.get_active_magnifier()
    if model is None:
        return None
    value = 0.5
    if isinstance(location, Point):
        value = location.x if not model.is_horizontal else location.y
    elif isinstance(location, (float, int)):
        value = float(location)
    value = max(0.0, min(1.0, value))
    if model.internal_split == value:
        return model
    result = scene_state.set_object_internal_split(model.id, value)
    store.emit_viewport_change()
    return result

def viewport_add_instance(store, position=None):
    from domain.types import Point
    from ..mode import MagnifierModeService
    from ..store import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    MagnifierModeService(store).prepare_for_add()

    # If no position specified, calculate offset from existing magnifiers
    if position is None:
        existing = list(MagnifierStoreService(store).iter_magnifiers())
        if existing:
            # Offset new magnifier slightly from the first one
            first = existing[0]
            offset_x = 0.15 if first.position.x < 0.5 else -0.15
            offset_y = 0.15 if first.position.y < 0.5 else -0.15
            position = Point(
                max(0.1, min(0.9, first.position.x + offset_x)),
                max(0.1, min(0.9, first.position.y + offset_y)),
            )

    model = MagnifierStoreService(store).add_magnifier(position=position)
    store.emit_viewport_change()
    return model

def viewport_remove_active_instance(store) -> bool:
    from ..mode import MagnifierModeService
    from ..store import MagnifierStoreService, active_magnifier_id

    if store is None or getattr(store, "viewport", None) is None:
        return False
    scene_state = MagnifierStoreService(store)
    if len(scene_state.iter_magnifiers()) <= 1:
        return False
    active = active_magnifier_id(store.viewport.view_state)
    if not active:
        return False
    scene_state.remove_object(active)
    MagnifierModeService(store).normalize_after_remove()
    # Note: normalize_after_remove already emits viewport change
    return True

def viewport_set_active_instance(store, magnifier_id: str):
    from ..store import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    result = MagnifierStoreService(store).set_active_object(magnifier_id)
    store.emit_viewport_change()
    return result

def viewport_set_instance_visibility(
    store,
    magnifier_id: str,
    visible: bool,
):
    from ..store import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    result = MagnifierStoreService(store).set_object_visibility(
        magnifier_id,
        bool(visible),
    )
    store.emit_viewport_change()
    return result

def viewport_set_all_freeze(
    store,
    freeze: bool,
    *,
    frozen_positions: dict[str, Any] | None = None,
    new_offsets: dict[str, Any] | None = None,
):
    from ..store import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    result = MagnifierStoreService(store).set_all_magnifiers_freeze(
        bool(freeze),
        frozen_positions=frozen_positions,
        new_offsets=new_offsets,
    )
    store.emit_viewport_change()
    return result

def viewport_set_active_freeze(
    store,
    freeze: bool,
):
    from ..store import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    scene_state = MagnifierStoreService(store)
    model = scene_state.get_active_or_first_magnifier()
    if model is None:
        return None
    frozen_position = model.position if freeze else None
    result = scene_state.set_active_magnifier_freeze(
        bool(freeze),
        frozen_position=frozen_position,
    )
    store.emit_viewport_change()
    return result

def viewport_set_active_combined(
    store,
    combined: bool,
):
    from ..store import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    scene_state = MagnifierStoreService(store)
    model = scene_state.get_active_or_first_magnifier()
    if model is None:
        return None
    result = scene_state.set_active_magnifier_spacing(
        0.0 if bool(combined) else max(float(model.spacing_relative), 0.05)
    )
    store.emit_viewport_change()
    return result
