from __future__ import annotations

import logging
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal

from core.events import (
    ViewportOnSliderPressedEvent,
    ViewportOnSliderReleasedEvent,
    ViewportSetMagnifierInternalSplitEvent,
    ViewportSetMagnifierPositionEvent,
    ViewportSetMagnifierVisibilityEvent,
    ViewportSetSplitPositionEvent,
    ViewportToggleFreezeMagnifierEvent,
    ViewportToggleMagnifierEvent,
    ViewportToggleMagnifierOrientationEvent,
    ViewportToggleMagnifierPartEvent,
    ViewportToggleOrientationEvent,
    ViewportUpdateCaptureSizeRelativeEvent,
    ViewportUpdateMagnifierCombinedStateEvent,
    ViewportUpdateMagnifierSizeRelativeEvent,
    ViewportUpdateMovementSpeedEvent,
)
from plugins.viewport.interaction_service import ViewportInteractionService
from plugins.viewport.magnifier_service import ViewportMagnifierService
from plugins.viewport.runtime import ViewportRuntime
from ui.canvas_features.magnifier import MagnifierModeService, MagnifierStoreService
from ui.canvas_features.magnifier.store import active_magnifier_id

logger = logging.getLogger("ImproveImgSLI")

class ViewportController(QObject):

    update_requested = pyqtSignal()
    start_interactive_movement = pyqtSignal()
    stop_interactive_movement = pyqtSignal()

    def __init__(self, store, magnifier_plugin=None, event_bus=None):
        super().__init__()
        self.store = store
        self.magnifier_plugin = magnifier_plugin
        self.event_bus = event_bus
        self.runtime = ViewportRuntime(
            store=store,
            event_bus=event_bus,
            update_requested_signal=self.update_requested,
        )
        self.scene_state = MagnifierStoreService(store)
        self.mode_state = MagnifierModeService(store)
        self.interaction_service = ViewportInteractionService(self.runtime, store)
        self.magnifier_service = ViewportMagnifierService(
            self.runtime, store, self.interaction_service
        )

    def _dispatch_action(
        self, action, clear_caches: bool = False, clamp_pos: bool = False
    ):
        if not self.runtime.dispatch(action, clear_caches=clear_caches):
            return
        if clamp_pos:
            self.interaction_service.clamp_capture_position()
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()

    def _capture_recording_checkpoint(self, *, force_advance_frame: bool = False) -> None:
        self.runtime.capture_recording_checkpoint(
            force_advance_frame=force_advance_frame
        )

    def begin_user_interaction(self) -> None:
        self.interaction_service.begin_user_interaction()

    def end_user_interaction(self) -> None:
        self.interaction_service.end_user_interaction()

    def set_split_position(self, position: float):
        from core.state_management.actions import SetSplitPositionAction

        clamped = max(0.0, min(1.0, position))
        self._dispatch_action(SetSplitPositionAction(clamped))

    def toggle_orientation(self, is_horizontal: bool):
        from core.state_management.actions import ToggleOrientationAction

        self._dispatch_action(ToggleOrientationAction(is_horizontal))

    def update_magnifier_size_relative(self, relative_size: float):
        self.scene_state.set_active_magnifier_size(relative_size)
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()

    def update_capture_size_relative(self, relative_size: float):
        self.scene_state.set_active_capture_size(relative_size)
        self.interaction_service.clamp_capture_position()
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()

    def toggle_magnifier(self, enabled: bool):
        self.mode_state.toggle_from_button(enabled)
        self.magnifier_service.update_combined_state()
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()

    def toggle_magnifier_part(self, part: str, visible: bool):
        part = (part or "").strip().lower()
        if part not in {"left", "center", "right"}:
            return
        self.scene_state.set_active_magnifier_visibility_parts(**{part: visible})
        self.magnifier_service.update_combined_state()
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()

    def set_magnifier_visibility(
        self,
        left: bool | None = None,
        center: bool | None = None,
        right: bool | None = None,
    ):
        self.scene_state.set_active_magnifier_visibility_parts(
            left=left,
            center=center,
            right=right,
        )
        self.magnifier_service.update_combined_state()
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()

    def toggle_magnifier_orientation(self, is_horizontal: bool):
        self.scene_state.set_active_magnifier_orientation(is_horizontal)
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()

    def toggle_freeze_magnifier(self, freeze_checked: bool):
        self.magnifier_service.toggle_freeze_magnifier(freeze_checked)

    def update_magnifier_combined_state(self):
        self.magnifier_service.update_combined_state()

    def update_movement_speed(self, speed: float):
        from core.state_management.actions import SetMovementSpeedAction

        self._dispatch_action(SetMovementSpeedAction(speed))

    def set_magnifier_position(self, position: Point):
        self.scene_state.move_object_source_position(
            active_magnifier_id(self.store.viewport.view_state),
            position,
        )
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()

    def set_magnifier_internal_split(self, location):
        self.magnifier_service.set_magnifier_internal_split(location)

    def on_slider_pressed(self, slider_name: str):
        from core.state_management.actions import SetIsDraggingSliderAction

        self.begin_user_interaction()
        self._dispatch_action(SetIsDraggingSliderAction(True))

    def on_slider_released(self, setting_name: str, value_to_save_provider):
        from core.state_management.actions import SetIsDraggingSliderAction

        self._dispatch_action(SetIsDraggingSliderAction(False))
        self.end_user_interaction()

    def _handle_slider_pressed_event(self, event: ViewportOnSliderPressedEvent):
        self.on_slider_pressed(event.slider_name)

    def _handle_slider_released_event(self, event: ViewportOnSliderReleasedEvent):
        self.on_slider_released(event.slider_name, event.provider)

    def _clamp_capture_position(self):
        self.interaction_service.clamp_capture_position()

    def on_set_split_position(self, event: ViewportSetSplitPositionEvent):
        self.set_split_position(event.position)

    def on_update_magnifier_size_relative(
        self, event: ViewportUpdateMagnifierSizeRelativeEvent
    ):
        self.update_magnifier_size_relative(event.relative_size)

    def on_update_capture_size_relative(
        self, event: ViewportUpdateCaptureSizeRelativeEvent
    ):
        self.update_capture_size_relative(event.relative_size)

    def on_update_movement_speed(self, event: ViewportUpdateMovementSpeedEvent):
        self.update_movement_speed(event.speed)

    def on_set_magnifier_position(self, event: ViewportSetMagnifierPositionEvent):
        self.set_magnifier_position(event.position)

    def on_set_magnifier_internal_split(
        self, event: ViewportSetMagnifierInternalSplitEvent
    ):
        self.set_magnifier_internal_split(event.split_position)

    def on_toggle_magnifier_part(self, event: ViewportToggleMagnifierPartEvent):
        self.toggle_magnifier_part(event.part, event.visible)

    def on_update_magnifier_combined_state(
        self, event: ViewportUpdateMagnifierCombinedStateEvent
    ):
        self.update_magnifier_combined_state()

    def on_toggle_orientation(self, event: ViewportToggleOrientationEvent):
        self.toggle_orientation(event.is_horizontal)

    def on_toggle_magnifier_orientation(
        self, event: ViewportToggleMagnifierOrientationEvent
    ):
        self.toggle_magnifier_orientation(event.is_horizontal)

    def on_toggle_freeze_magnifier(self, event: ViewportToggleFreezeMagnifierEvent):
        self.toggle_freeze_magnifier(event.freeze)

    def on_set_magnifier_visibility(self, event: ViewportSetMagnifierVisibilityEvent):
        self.set_magnifier_visibility(event.left, event.center, event.right)

    def on_toggle_magnifier(self, event: ViewportToggleMagnifierEvent):
        self.toggle_magnifier(event.enabled)
