from __future__ import annotations

import logging
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal

from domain.types import Point
from plugins.viewport.events import (
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
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias

logger = logging.getLogger("ImproveImgSLI")

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

class ViewportController(QObject):

    update_requested = pyqtSignal()
    start_interactive_movement = pyqtSignal()
    stop_interactive_movement = pyqtSignal()

    def __init__(self, store, event_bus=None, settings_manager=None):
        super().__init__()
        self.store = store
        self.event_bus = event_bus
        self._settings_manager = settings_manager
        self.runtime = ViewportRuntime(
            store=store,
            event_bus=event_bus,
            update_requested_signal=self.update_requested,
        )
        self.interaction_service = ViewportInteractionService(self.runtime, store)
        self.magnifier_service = ViewportMagnifierService(
            self.runtime, store, self.interaction_service
        )

    def _save_setting(self, key: str, value) -> None:
        if self._settings_manager is not None:
            self._settings_manager._save_setting(key, value)

    def _sync_settings(self) -> None:
        if self._settings_manager is not None:
            self._settings_manager.settings.sync()

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
        self.toggle_magnifier_orientation(is_horizontal)
        self._save_setting("is_horizontal", is_horizontal)
        self._save_setting("magnifier_layout_horizontal", is_horizontal)

    def update_magnifier_size_relative(self, relative_size: float):
        _execute_magnifier_command(self.store, "overlay.set_active_size", relative_size)
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()

    def update_capture_size_relative(self, relative_size: float):
        _execute_magnifier_command(
            self.store,
            "overlay.set_active_capture_size",
            relative_size,
        )
        self.interaction_service.clamp_capture_position()
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()

    def toggle_magnifier(self, enabled: bool):
        _execute_magnifier_command(self.store, "overlay.toggle_enabled", enabled)
        self.magnifier_service.update_combined_state()
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()
        self._save_setting("use_magnifier", bool(self.is_magnifier_enabled()))
        self._sync_settings()

    def should_show_magnifier_panel(self) -> bool:
        return bool(_query_magnifier(self.store, "overlay.should_show_panel", False))

    def is_magnifier_enabled(self) -> bool:
        return bool(_query_magnifier(self.store, "overlay.enabled", False))

    def toggle_magnifier_part(self, part: str, visible: bool):
        part = (part or "").strip().lower()
        if part not in {"left", "center", "right"}:
            return
        _execute_magnifier_command(
            self.store,
            "overlay.set_active_visibility_parts",
            **{part: visible},
        )
        self.magnifier_service.update_combined_state()
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()

    def set_magnifier_visibility(
        self,
        left: bool | None = None,
        center: bool | None = None,
        right: bool | None = None,
    ):
        _execute_magnifier_command(
            self.store,
            "overlay.set_active_visibility_parts",
            left=left,
            center=center,
            right=right,
        )
        self.magnifier_service.update_combined_state()
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()

    def toggle_magnifier_orientation(self, is_horizontal: bool):
        _execute_magnifier_command(
            self.store,
            "overlay.set_active_orientation",
            is_horizontal,
        )
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()
        self._save_setting("magnifier_layout_horizontal", is_horizontal)

    def toggle_freeze_magnifier(self, freeze_checked: bool):
        self.magnifier_service.toggle_freeze_magnifier(freeze_checked)
        self._save_setting("magnifier_freeze", freeze_checked)

    def update_magnifier_combined_state(self):
        self.magnifier_service.update_combined_state()

    def update_movement_speed(self, speed: float):
        from core.state_management.actions import SetMovementSpeedAction

        self._dispatch_action(SetMovementSpeedAction(speed))

    def set_magnifier_position(self, position: Point):
        _execute_magnifier_command(
            self.store,
            "overlay.move_active_position",
            position,
        )
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()

    def set_magnifier_internal_split(self, location):
        self.magnifier_service.set_magnifier_internal_split(location)

    @staticmethod
    def _resolve_new_magnifier_position(active) -> Point:
        if active is None:
            return Point(0.5, 0.5)

        position = (
            active.get("position")
            if isinstance(active, dict)
            else getattr(active, "position", None)
        )
        if position is None:
            return Point(0.5, 0.5)

        base_x = float(position.x)
        base_y = float(position.y)
        size = float(
            active.get("size_relative", 0.2)
            if isinstance(active, dict)
            else getattr(active, "size_relative", 0.2)
            or 0.2
        )
        step = max(0.06, min(0.32, size * 1.25))

        dir_x = -1.0 if base_x >= 0.7 else 1.0
        dir_y = -1.0 if base_y >= 0.7 else 1.0

        capture_size = float(
            active.get("capture_size_relative", 0.1)
            if isinstance(active, dict)
            else getattr(active, "capture_size_relative", 0.1)
            or 0.1
        )
        safe_margin = max(0.05, min(0.2, capture_size * 0.6))
        min_pos = safe_margin
        max_pos = 1.0 - safe_margin
        if min_pos > max_pos:
            min_pos, max_pos = 0.1, 0.9

        return Point(
            max(min_pos, min(max_pos, base_x + (dir_x * step))),
            max(min_pos, min(max_pos, base_y + (dir_y * step))),
        )

    def add_magnifier(self, position: Point | None = None):
        if position is None:
            active = _query_magnifier(self.store, "overlay.active_state")
            position = self._resolve_new_magnifier_position(active)
        _execute_magnifier_command(
            self.store,
            "overlay.add_instance",
            position=position,
        )
        self.store.invalidate_render_cache()
        self.store.emit_state_change()
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()

    def remove_active_magnifier(self):
        removed = _execute_magnifier_command(
            self.store,
            "overlay.remove_active_instance",
        )
        if not removed:
            return
        self.store.invalidate_render_cache()
        self.store.emit_state_change()
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()

    def set_active_magnifier(self, mag_id: str):
        _execute_magnifier_command(
            self.store,
            "overlay.set_active_instance",
            mag_id,
        )
        self.store.invalidate_render_cache()
        self.store.emit_state_change()
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()

    def toggle_magnifier_instance_visibility(self, mag_id: str, visible: bool):
        _execute_magnifier_command(
            self.store,
            "overlay.set_instance_visibility",
            mag_id,
            visible,
        )
        self.store.invalidate_render_cache()
        self.store.emit_state_change()
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()

    def toggle_magnifier_guides(self, enabled: bool):
        toggle_cmd = get_canvas_feature_command_by_alias("guides.toggle_enabled")
        if toggle_cmd is not None:
            toggle_cmd(self.store, enabled)
        self.store.emit_state_change()
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()

    def set_magnifier_guides_thickness(self, thickness: int):
        set_thickness_cmd = get_canvas_feature_command_by_alias("guides.set_thickness")
        if set_thickness_cmd is not None:
            set_thickness_cmd(self.store, thickness)
        self.store.emit_state_change()
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()

    def on_slider_pressed(self, slider_name: str):
        from core.state_management.actions import SetIsDraggingSliderAction

        self.begin_user_interaction()
        self._dispatch_action(SetIsDraggingSliderAction(True))

    def on_slider_released(self, setting_name: str, value_to_save_provider=None):
        from core.state_management.actions import SetIsDraggingSliderAction

        self._dispatch_action(SetIsDraggingSliderAction(False))
        self.end_user_interaction()
        if setting_name and value_to_save_provider is not None:
            self._save_setting(setting_name, value_to_save_provider())

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

    def toggle_magnifier_laser(self, enabled: bool):
        from plugins.viewport.actions import SetMagnifierLaserEnabledAction
        self._dispatch_action(SetMagnifierLaserEnabledAction(enabled))
        self.runtime.emit_update(scope="viewport")

    def on_toggle_magnifier_part(self, event: ViewportToggleMagnifierPartEvent):
        self.toggle_magnifier_part(event.part, event.visible)

    def on_toggle_magnifier_laser(self, event):
        self.toggle_magnifier_laser(event.enabled)

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

    def set_magnifier_divider_thickness(self, thickness: int):
        set_thickness_cmd = get_canvas_feature_command_by_alias("splitter.set_thickness")
        if set_thickness_cmd is not None:
            set_thickness_cmd(self.store, thickness)
        self.store.emit_state_change()
        self.runtime.emit_update(scope="viewport")
        self.runtime.capture_recording_checkpoint()

    def toggle_include_filenames_in_saved(self, include_checked: bool):
        vp = self.store.viewport if self.store else None
        if vp and vp.render_config.include_file_names_in_saved != include_checked:
            dispatcher = getattr(self.store, "_dispatcher", None)
            if dispatcher:
                from core.state_management.actions import (
                    InvalidateRenderCacheAction,
                    SetIncludeFileNamesInSavedAction,
                )

                dispatcher.dispatch(
                    SetIncludeFileNamesInSavedAction(include_checked),
                    scope="viewport",
                )
                dispatcher.dispatch(InvalidateRenderCacheAction(), scope="viewport")
            else:
                vp.render_config.include_file_names_in_saved = include_checked
                self.store.invalidate_render_cache()
            self.store.emit_state_change()
            self.runtime.emit_update(scope="viewport")

        self._save_setting("include_file_names_in_saved", include_checked)
        self._sync_settings()
