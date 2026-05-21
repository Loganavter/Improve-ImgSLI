from __future__ import annotations

from typing import Any

from ..state import get_magnifier_widget_state

def _serialize_magnifier_model(model) -> dict[str, Any]:
    return {
        "id": model.id,
        "position": model.position,
        "size_relative": float(model.size_relative),
        "capture_size_relative": float(model.capture_size_relative),
        "is_horizontal": bool(model.is_horizontal),
        "freeze": bool(model.freeze),
        "frozen_position": model.frozen_position,
        "offset_relative": model.offset_relative,
        "spacing_relative": float(model.spacing_relative),
        "internal_split": float(model.internal_split),
        "visible": bool(model.visible),
        "visible_left": bool(model.visible_left),
        "visible_center": bool(model.visible_center),
        "visible_right": bool(model.visible_right),
        "border_color": model.border_color,
        "divider_color": model.divider_color,
        "divider_visible": bool(getattr(model, "divider_visible", False)),
        "divider_thickness": float(getattr(model, "divider_thickness", 0)),
        "capture_color": getattr(model, "capture_color", None),
        "guides_color": getattr(model, "guides_color", None),
        "show_laser": bool(getattr(model, "show_laser", True)),
    }

def query_is_horizontal(store) -> bool:
    from ..store import MagnifierStoreService

    model = MagnifierStoreService(store).get_active_or_first_magnifier()
    return bool(model.is_horizontal) if model is not None else False

def query_active_magnifier_state(store) -> dict[str, Any] | None:
    from ..store import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    model = MagnifierStoreService(store).get_active_or_first_magnifier()
    if model is None:
        return None
    return _serialize_magnifier_model(model)

def query_total_count(store) -> int:
    from ..mode import MagnifierModeService

    if store is None or getattr(store, "viewport", None) is None:
        return 0
    return int(MagnifierModeService(store).total_count())

def query_all_magnifier_states(store) -> tuple[dict[str, Any], ...]:
    from ..store import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return ()
    states: list[dict[str, Any]] = []
    for model in MagnifierStoreService(store).iter_magnifiers():
        states.append(_serialize_magnifier_model(model))
    return tuple(states)

def query_spacing_limits(_store) -> dict[str, float]:
    from ..constants import (
        MAX_MAGNIFIER_SPACING_RELATIVE,
        MIN_MAGNIFIER_SPACING_RELATIVE,
    )

    return {
        "min": float(MIN_MAGNIFIER_SPACING_RELATIVE),
        "max": float(MAX_MAGNIFIER_SPACING_RELATIVE),
    }

def query_behavior_settings(store) -> dict[str, bool]:
    if store is None or getattr(store, "viewport", None) is None:
        return {
            "intersection_highlight_enabled": False,
            "auto_color_new_instances": False,
        }
    state = get_magnifier_widget_state(store.viewport.view_state)
    return {
        "intersection_highlight_enabled": bool(state.intersection_highlight_enabled),
        "auto_color_new_instances": bool(state.auto_color_new_instances),
    }

def query_should_show_panel(store) -> bool:
    from ..mode import MagnifierModeService

    if store is None or getattr(store, "viewport", None) is None:
        return False
    return bool(MagnifierModeService(store).should_show_panel())

def query_are_all_frozen(store) -> bool:
    from ..store import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return False
    return bool(MagnifierStoreService(store).are_all_magnifiers_frozen())

def query_active_combined(store) -> bool:
    from ..store import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return False
    return bool(MagnifierStoreService(store).is_active_magnifier_combined())

def query_active_divider_color(store):
    from ..store import active_or_default_divider_color

    if store is None or getattr(store, "viewport", None) is None:
        return None
    return active_or_default_divider_color(store.viewport.view_state)

def query_active_divider_visible(store) -> bool:
    from ..store import active_or_default_divider_visible

    if store is None or getattr(store, "viewport", None) is None:
        return False
    return bool(active_or_default_divider_visible(store.viewport.view_state))

def query_active_border_color(store):
    from ..store import active_or_default_border_color

    if store is None or getattr(store, "viewport", None) is None:
        return None
    return active_or_default_border_color(store.viewport.view_state)

def query_active_capture_size(store) -> float:
    from ..store import MagnifierStoreService, default_capture_size

    if store is None or getattr(store, "viewport", None) is None:
        return 0.1
    model = MagnifierStoreService(store).get_active_or_first_magnifier()
    if model is None:
        return float(default_capture_size(store.viewport.view_state))
    return float(model.capture_size_relative)

class MagnifierMovementHandler:
    def __init__(self, store):
        self._store = store

    def _svc(self):
        from ..store import MagnifierStoreService

        return MagnifierStoreService(self._store)

    def _model(self):
        return self._svc().get_active_or_first_magnifier()

    def get_offset(self):
        model = self._model()
        return model.offset_relative if model is not None else None

    def get_spacing(self):
        model = self._model()
        return float(model.spacing_relative) if model is not None else None

    def get_internal_split(self):
        model = self._model()
        return float(model.internal_split) if model is not None else None

    def has_both_sides(self) -> bool:
        model = self._model()
        if model is None:
            return False
        return bool(getattr(model, "visible_left", False)) and bool(
            getattr(model, "visible_right", False)
        )

    def set_offset(self, offset):
        self._svc().set_active_magnifier_offset(offset)

    def set_spacing(self, spacing: float):
        self._svc().set_active_magnifier_spacing(spacing)

    def get_spacing_limits(self) -> tuple[float, float]:
        limits = query_spacing_limits(self._store)
        return (limits["min"], limits["max"])

    def emit_combined_state(self, event_bus=None):
        if event_bus is None:
            return
        # Notify magnifier to recalculate combined state via Feature State API
        from ui.canvas_infra.scene.feature_state_api import execute_feature_command, query_feature_state
        if self._store is not None:
            # Query current combined state and preserve it (don't toggle)
            active_state = query_feature_state(self._store, "magnifier", "active_state")
            current_spacing = active_state.get("spacing_relative", 0.05) if active_state else 0.05
            combined = current_spacing == 0.0
            execute_feature_command(self._store, "magnifier", "set_active_combined", combined)

def emit_overlay_changed(store, *, event_bus=None):
    if event_bus is None and store is None:
        return
    # Notify magnifier to recalculate combined state via Feature State API
    from ui.canvas_infra.scene.feature_state_api import execute_feature_command, query_feature_state
    if store is not None:
        # Query current combined state and preserve it (don't toggle)
        active_state = query_feature_state(store, "magnifier", "active_state")
        current_spacing = active_state.get("spacing_relative", 0.05) if active_state else 0.05
        combined = current_spacing == 0.0
        execute_feature_command(store, "magnifier", "set_active_combined", combined)

def get_movement_handler(store):
    if store is None or getattr(store, "viewport", None) is None:
        return None
    return MagnifierMovementHandler(store)
