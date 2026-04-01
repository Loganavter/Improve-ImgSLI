from __future__ import annotations

from domain.types import Point

try:
    from core.constants import AppConstants

    THRESHOLD = AppConstants.MIN_MAGNIFIER_SPACING_RELATIVE_FOR_COMBINE
except ImportError:
    THRESHOLD = 0.02

class ViewportMagnifierService:
    def __init__(self, runtime, store, interaction_service):
        self.runtime = runtime
        self.store = store
        self.interaction_service = interaction_service

    def set_magnifier_internal_split(self, location):
        val = 0.5
        if isinstance(location, Point):
            val = (
                location.x
                if not self.store.viewport.view_state.magnifier_is_horizontal
                else location.y
            )
        elif isinstance(location, (float, int)):
            val = float(location)

        val = max(0.0, min(1.0, val))
        if self.store.viewport.view_state.magnifier_internal_split == val:
            return

        from core.state_management.actions import SetMagnifierInternalSplitAction

        self.runtime.dispatch(SetMagnifierInternalSplitAction(val))
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()

    def toggle_freeze_magnifier(self, freeze_checked: bool):
        from core.state_management.actions import ToggleFreezeMagnifierAction

        if freeze_checked:
            frozen_point = self.store.viewport.view_state.capture_position_relative
            self.runtime.dispatch(
                ToggleFreezeMagnifierAction(freeze=True, frozen_position=frozen_point)
            )
        else:
            self.runtime.dispatch(
                ToggleFreezeMagnifierAction(
                    freeze=False,
                    new_offset=self.interaction_service.compute_unfreeze_offset(),
                )
            )
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()

    def update_combined_state(self):
        from core.state_management.actions import UpdateMagnifierCombinedStateAction

        if not self.store.viewport.view_state.use_magnifier:
            self.runtime.dispatch(
                UpdateMagnifierCombinedStateAction(False), clear_caches=True
            )
            self.runtime.emit_update(scope="viewport")
            self.runtime.capture_recording_checkpoint()
            return

        spacing = self.store.viewport.view_state.magnifier_spacing_relative
        both_sides_visible = (
            self.store.viewport.view_state.magnifier_visible_left
            and self.store.viewport.view_state.magnifier_visible_right
        )
        should_combine = both_sides_visible and spacing <= THRESHOLD + 1e-5
        if self.store.viewport.view_state.is_magnifier_combined == should_combine:
            return

        self.runtime.dispatch(
            UpdateMagnifierCombinedStateAction(should_combine), clear_caches=True
        )
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()
