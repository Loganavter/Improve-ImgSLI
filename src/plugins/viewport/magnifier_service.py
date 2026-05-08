from __future__ import annotations

from domain.types import Point
from ui.canvas_features.magnifier import MagnifierStoreService
from ui.canvas_features.magnifier.store import magnifier_enabled

class ViewportMagnifierService:
    def __init__(self, runtime, store, interaction_service):
        self.runtime = runtime
        self.store = store
        self.interaction_service = interaction_service
        self.scene_state = MagnifierStoreService(store)

    def set_magnifier_internal_split(self, location):
        model = self.scene_state.get_active_magnifier()
        if model is None:
            return
        val = 0.5
        if isinstance(location, Point):
            val = (
                location.x
                if not model.is_horizontal
                else location.y
            )
        elif isinstance(location, (float, int)):
            val = float(location)

        val = max(0.0, min(1.0, val))
        if model.internal_split == val:
            return

        self.scene_state.set_object_internal_split(model.id, val)
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()

    def toggle_freeze_magnifier(self, freeze_checked: bool):
        models = list(self.scene_state.iter_magnifiers())
        if not models:
            return
        if freeze_checked:
            self.scene_state.set_all_magnifiers_freeze(
                True,
                frozen_positions={model.id: model.position for model in models},
            )
        else:
            self.scene_state.set_all_magnifiers_freeze(
                False,
                new_offsets={
                    model.id: self.interaction_service.compute_unfreeze_offset_for(model)
                    for model in models
                },
            )
        self.store.invalidate_render_cache()
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()

    def update_combined_state(self):
        if not magnifier_enabled(self.store.viewport.view_state):
            self.runtime.emit_update(scope="viewport")
            self.runtime.capture_recording_checkpoint()
            return

        current = self.scene_state.is_active_magnifier_combined()
        should_combine = self.scene_state.update_active_magnifier_combined_state()
        if current == should_combine:
            return

        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()
