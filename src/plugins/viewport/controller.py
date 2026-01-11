from __future__ import annotations
import logging
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal, QPointF
from core.events import (
    CoreUpdateRequestedEvent,
    ViewportSetSplitPositionEvent,
    ViewportUpdateMagnifierSizeRelativeEvent,
    ViewportUpdateCaptureSizeRelativeEvent,
    ViewportUpdateMovementSpeedEvent,
    ViewportSetMagnifierPositionEvent,
    ViewportSetMagnifierInternalSplitEvent,
    ViewportToggleMagnifierPartEvent,
    ViewportUpdateMagnifierCombinedStateEvent,
    ViewportToggleOrientationEvent,
    ViewportToggleMagnifierOrientationEvent,
    ViewportToggleFreezeMagnifierEvent,
    ViewportOnSliderPressedEvent,
    ViewportOnSliderReleasedEvent,
    ViewportSetMagnifierVisibilityEvent,
    ViewportToggleMagnifierEvent,
)
try:
    from core.constants import AppConstants
    THRESHOLD = AppConstants.MIN_MAGNIFIER_SPACING_RELATIVE_FOR_COMBINE
except ImportError:
    THRESHOLD = 0.02

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
        self._dispatcher = store.get_dispatcher() if hasattr(store, 'get_dispatcher') else None

    def _dispatch_action(self, action, clear_caches: bool = False, clamp_pos: bool = False):
        if self._dispatcher:
            self._dispatcher.dispatch(action, scope="viewport")
            if clear_caches:
                from core.state_management.actions import InvalidateRenderCacheAction
                self._dispatcher.dispatch(InvalidateRenderCacheAction(), scope="viewport")
            if clamp_pos:
                self._clamp_capture_position()

            if self.event_bus:
                self.event_bus.emit(CoreUpdateRequestedEvent())
            else:
                self.update_requested.emit()
        else:

            logger.warning("Dispatcher not available, using legacy state modification")

            pass

    def _update_setting(self, attr_name: str, value: Any, clear_caches: bool = False, clamp_pos: bool = False):
        current_val = getattr(self.store.viewport, attr_name, None)

        if current_val != value:
            setattr(self.store.viewport, attr_name, value)

            if clear_caches:
                self.store.invalidate_render_cache()

            if clamp_pos:
                self._clamp_capture_position()

            self.store.emit_state_change()

            if self.event_bus:
                self.event_bus.emit(CoreUpdateRequestedEvent())
            else:
                self.update_requested.emit()

    def set_split_position(self, position: float):
        from core.state_management.actions import SetSplitPositionAction
        clamped = max(0.0, min(1.0, position))
        self._dispatch_action(SetSplitPositionAction(clamped))

    def toggle_orientation(self, is_horizontal: bool):
        from core.state_management.actions import ToggleOrientationAction
        self._dispatch_action(ToggleOrientationAction(is_horizontal))

    def update_magnifier_size_relative(self, relative_size: float):
        from core.state_management.actions import SetMagnifierSizeRelativeAction
        self._dispatch_action(SetMagnifierSizeRelativeAction(relative_size))

    def update_capture_size_relative(self, relative_size: float):
        from core.state_management.actions import SetCaptureSizeRelativeAction
        self._dispatch_action(SetCaptureSizeRelativeAction(relative_size), clear_caches=True, clamp_pos=True)

    def toggle_magnifier(self, enabled: bool):
        from core.state_management.actions import ToggleMagnifierAction, SetActiveMagnifierIdAction
        self._dispatch_action(ToggleMagnifierAction(enabled))

        if enabled and not self.store.viewport.active_magnifier_id:
            self._dispatch_action(SetActiveMagnifierIdAction("default"))

        self.update_magnifier_combined_state()

    def toggle_magnifier_part(self, part: str, visible: bool):
        part = (part or "").strip().lower()
        mapping = {
            "left": "magnifier_visible_left",
            "center": "magnifier_visible_center",
            "right": "magnifier_visible_right",
        }
        if part not in mapping:
            return

        from core.state_management.actions import SetMagnifierVisibilityAction
        kwargs = {part: visible}
        self._dispatch_action(SetMagnifierVisibilityAction(**kwargs), clear_caches=True)
        self.update_magnifier_combined_state()

    def set_magnifier_visibility(self, left: bool | None = None, center: bool | None = None, right: bool | None = None):
        from core.state_management.actions import SetMagnifierVisibilityAction
        self._dispatch_action(SetMagnifierVisibilityAction(left=left, center=center, right=right), clear_caches=True)
        self.update_magnifier_combined_state()

    def toggle_magnifier_orientation(self, is_horizontal: bool):
        from core.state_management.actions import ToggleMagnifierOrientationAction
        self._dispatch_action(ToggleMagnifierOrientationAction(is_horizontal))

    def toggle_freeze_magnifier(self, freeze_checked: bool):
        from core.state_management.actions import ToggleFreezeMagnifierAction

        if freeze_checked:
            frozen_point = QPointF(self.store.viewport.capture_position_relative)
            self._dispatch_action(ToggleFreezeMagnifierAction(
                freeze=True,
                frozen_position=frozen_point
            ))
        else:
            new_offset = None
            if self.store.viewport.frozen_capture_point_relative:
                drawing_width = self.store.viewport.pixmap_width
                drawing_height = self.store.viewport.pixmap_height

                if drawing_width > 0 and drawing_height > 0:
                    target_max_dim = float(max(drawing_width, drawing_height))

                    frozen_capture_pixels = QPointF(
                        self.store.viewport.frozen_capture_point_relative.x() * drawing_width,
                        self.store.viewport.frozen_capture_point_relative.y() * drawing_height,
                    )
                    current_offset_pixels = QPointF(
                        self.store.viewport.magnifier_offset_relative.x() * target_max_dim,
                        self.store.viewport.magnifier_offset_relative.y() * target_max_dim,
                    )
                    target_magnifier_pos_pixels = frozen_capture_pixels + current_offset_pixels

                    new_capture_pos_pixels = QPointF(
                        self.store.viewport.capture_position_relative.x() * drawing_width,
                        self.store.viewport.capture_position_relative.y() * drawing_height,
                    )

                    new_offset_pixels = target_magnifier_pos_pixels - new_capture_pos_pixels

                    new_offset_relative = QPointF(
                        new_offset_pixels.x() / target_max_dim if target_max_dim > 0 else 0,
                        new_offset_pixels.y() / target_max_dim if target_max_dim > 0 else 0,
                    )
                    new_offset = new_offset_relative

            self._dispatch_action(ToggleFreezeMagnifierAction(
                freeze=False,
                new_offset=new_offset
            ))

    def update_magnifier_combined_state(self):
        if not self.store.viewport.use_magnifier:
            from core.state_management.actions import UpdateMagnifierCombinedStateAction
            self._dispatch_action(UpdateMagnifierCombinedStateAction(False), clear_caches=True)
            return

        is_diff_active = self.store.viewport.diff_mode != 'off'
        spacing = self.store.viewport.magnifier_spacing_relative

        should_combine = spacing <= THRESHOLD + 1e-5

        if self.store.viewport.is_magnifier_combined != should_combine:
            from core.state_management.actions import UpdateMagnifierCombinedStateAction
            self._dispatch_action(UpdateMagnifierCombinedStateAction(should_combine), clear_caches=True)

    def update_movement_speed(self, speed: float):
        from core.state_management.actions import SetMovementSpeedAction
        self._dispatch_action(SetMovementSpeedAction(speed))

    def set_magnifier_position(self, position: QPointF):
        from core.state_management.actions import SetMagnifierPositionAction
        self._dispatch_action(SetMagnifierPositionAction(position))

    def set_magnifier_internal_split(self, location: QPointF):
        val = 0.5
        if isinstance(location, QPointF):
            if not self.store.viewport.magnifier_is_horizontal:
                val = location.x()
            else:
                val = location.y()
        elif isinstance(location, (float, int)):
            val = float(location)

        val = max(0.0, min(1.0, val))
        current_val = self.store.viewport.magnifier_internal_split

        if current_val != val:
            from core.state_management.actions import SetMagnifierInternalSplitAction
            self._dispatch_action(SetMagnifierInternalSplitAction(val))

    def on_slider_pressed(self, slider_name: str):
        from core.state_management.actions import SetIsDraggingSliderAction
        self._dispatch_action(SetIsDraggingSliderAction(True))

    def on_slider_released(self, setting_name: str, value_to_save_provider):
        from core.state_management.actions import SetIsDraggingSliderAction
        self._dispatch_action(SetIsDraggingSliderAction(False))

    def _handle_slider_pressed_event(self, event: ViewportOnSliderPressedEvent):
        self.on_slider_pressed(event.slider_name)

    def _handle_slider_released_event(self, event: ViewportOnSliderReleasedEvent):
        self.on_slider_released(event.slider_name, event.provider)

    def _clamp_capture_position(self):
        capture_pos = self.store.viewport.capture_position_relative
        if not self.store.viewport.image1:
            return

        unified_w, unified_h = self.store.viewport.image1.size
        if unified_w <= 0 or unified_h <= 0:
            return

        ref_dim = min(unified_w, unified_h)
        capture_size_px = self.store.viewport.capture_size_relative * ref_dim
        radius_rel_x = (capture_size_px / 2.0) / unified_w if unified_w > 0 else 0
        radius_rel_y = (capture_size_px / 2.0) / unified_h if unified_h > 0 else 0

        self.store.viewport.capture_position_relative = QPointF(
            max(radius_rel_x, min(capture_pos.x(), 1.0 - radius_rel_x)),
            max(radius_rel_y, min(capture_pos.y(), 1.0 - radius_rel_y)),
        )

    def on_set_split_position(self, event: ViewportSetSplitPositionEvent):
        self.set_split_position(event.position)

    def on_update_magnifier_size_relative(self, event: ViewportUpdateMagnifierSizeRelativeEvent):
        self.update_magnifier_size_relative(event.relative_size)

    def on_update_capture_size_relative(self, event: ViewportUpdateCaptureSizeRelativeEvent):
        self.update_capture_size_relative(event.relative_size)

    def on_update_movement_speed(self, event: ViewportUpdateMovementSpeedEvent):
        self.update_movement_speed(event.speed)

    def on_set_magnifier_position(self, event: ViewportSetMagnifierPositionEvent):
        self.set_magnifier_position(event.position)

    def on_set_magnifier_internal_split(self, event: ViewportSetMagnifierInternalSplitEvent):
        self.set_magnifier_internal_split(event.split_position)

    def on_toggle_magnifier_part(self, event: ViewportToggleMagnifierPartEvent):
        self.toggle_magnifier_part(event.part, event.visible)

    def on_update_magnifier_combined_state(self, event: ViewportUpdateMagnifierCombinedStateEvent):
        self.update_magnifier_combined_state()

    def on_toggle_orientation(self, event: ViewportToggleOrientationEvent):
        self.toggle_orientation(event.is_horizontal)

    def on_toggle_magnifier_orientation(self, event: ViewportToggleMagnifierOrientationEvent):
        self.toggle_magnifier_orientation(event.is_horizontal)

    def on_toggle_freeze_magnifier(self, event: ViewportToggleFreezeMagnifierEvent):
        self.toggle_freeze_magnifier(event.freeze)

    def on_set_magnifier_visibility(self, event: ViewportSetMagnifierVisibilityEvent):
        self.set_magnifier_visibility(event.left, event.center, event.right)

    def on_toggle_magnifier(self, event: ViewportToggleMagnifierEvent):
        self.toggle_magnifier(event.enabled)
