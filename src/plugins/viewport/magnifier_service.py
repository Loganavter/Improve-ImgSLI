from __future__ import annotations

from domain.types import Point
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias

def _execute_magnifier_command(store, command_id: str, *args, **kwargs):
    command = get_canvas_feature_command_by_alias(command_id)
    if command is None:
        return None
    return command(store, *args, **kwargs)

def _query_magnifier(store, query_id: str, default=None, *args, **kwargs):
    command = get_canvas_feature_command_by_alias(query_id)
    if command is None:
        return default
    result = command(store, *args, **kwargs)
    return default if result is None else result

class ViewportMagnifierService:
    def __init__(self, runtime, store, interaction_service):
        self.runtime = runtime
        self.store = store
        self.interaction_service = interaction_service

    def set_magnifier_internal_split(self, location):
        model = _query_magnifier(self.store, "overlay.active_state")
        if model is None:
            return
        val = 0.5
        if isinstance(location, Point):
            val = (
                location.x
                if not model["is_horizontal"]
                else location.y
            )
        elif isinstance(location, (float, int)):
            val = float(location)

        val = max(0.0, min(1.0, val))
        if float(model["internal_split"]) == val:
            return

        _execute_magnifier_command(
            self.store,
            "overlay.set_internal_split",
            val,
        )
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()

    def toggle_freeze_magnifier(self, freeze_checked: bool):
        models = tuple(_query_magnifier(self.store, "overlay.all_states", ()) or ())
        if not models:
            return
        if freeze_checked:
            _execute_magnifier_command(
                self.store,
                "overlay.set_all_freeze",
                True,
                frozen_positions={model["id"]: model["position"] for model in models},
            )
        else:
            _execute_magnifier_command(
                self.store,
                "overlay.set_all_freeze",
                False,
                new_offsets={
                    model["id"]: self.interaction_service.compute_unfreeze_offset_for(model)
                    for model in models
                },
            )
        self.store.invalidate_render_cache()
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()

    def update_combined_state(self):
        if not bool(_query_magnifier(self.store, "overlay.enabled", False)):
            self.runtime.emit_update(scope="viewport")
            self.runtime.capture_recording_checkpoint()
            return

        current = bool(_query_magnifier(self.store, "overlay.active_combined", False))
        should_combine = bool(_query_magnifier(self.store, "overlay.active_combined", False))
        if current == should_combine:
            return

        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()
