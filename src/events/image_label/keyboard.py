from __future__ import annotations

from PyQt6.QtCore import Qt

class ImageLabelKeyboardHandler:
    MAGNIFIER_KEYS = {
        Qt.Key.Key_W,
        Qt.Key.Key_A,
        Qt.Key.Key_S,
        Qt.Key.Key_D,
        Qt.Key.Key_Q,
        Qt.Key.Key_E,
    }

    def __init__(self, handler):
        self.handler = handler

    @staticmethod
    def _update_axis_priority_on_press(viewport, key: int) -> None:
        if key in (Qt.Key.Key_A, Qt.Key.Key_D):
            viewport.interaction_state.last_horizontal_movement_key = key
        elif key in (Qt.Key.Key_W, Qt.Key.Key_S):
            viewport.interaction_state.last_vertical_movement_key = key
        elif key in (Qt.Key.Key_Q, Qt.Key.Key_E):
            viewport.interaction_state.last_spacing_movement_key = key

    @staticmethod
    def _update_axis_priority_on_release(viewport, key: int) -> None:
        if key in (Qt.Key.Key_A, Qt.Key.Key_D):
            if viewport.interaction_state.last_horizontal_movement_key == key:
                opposite = Qt.Key.Key_D if key == Qt.Key.Key_A else Qt.Key.Key_A
                viewport.interaction_state.last_horizontal_movement_key = (
                    opposite if opposite in viewport.interaction_state.pressed_keys else None
                )
        elif key in (Qt.Key.Key_W, Qt.Key.Key_S):
            if viewport.interaction_state.last_vertical_movement_key == key:
                opposite = Qt.Key.Key_S if key == Qt.Key.Key_W else Qt.Key.Key_W
                viewport.interaction_state.last_vertical_movement_key = (
                    opposite if opposite in viewport.interaction_state.pressed_keys else None
                )
        elif key in (Qt.Key.Key_Q, Qt.Key.Key_E):
            if viewport.interaction_state.last_spacing_movement_key == key:
                opposite = Qt.Key.Key_E if key == Qt.Key.Key_Q else Qt.Key.Key_Q
                viewport.interaction_state.last_spacing_movement_key = (
                    opposite if opposite in viewport.interaction_state.pressed_keys else None
                )

    def handle_key_press(self, event) -> None:
        key = event.key()
        viewport = self.handler.store.viewport
        if key == Qt.Key.Key_Space:
            if event.isAutoRepeat():
                return
            viewport.interaction_state.space_bar_pressed = True
            self.handler.store.emit_viewport_change("interaction")
            self.handler.preview.log_preview_debug("space_pressed")
            event.accept()
            return

        if key in self.MAGNIFIER_KEYS and event.isAutoRepeat():
            event.accept()
            return

        if key == Qt.Key.Key_Shift and self.handler.preview.is_active:
            self.handler.preview.log_preview_debug("shift_pressed_during_shift_preview")
            event.accept()
            return

        if key in self.MAGNIFIER_KEYS and viewport.view_state.use_magnifier and self.handler.main_controller:
            self.handler.main_controller.start_interactive_movement.emit()

        viewport.interaction_state.pressed_keys.add(key)
        if key in self.MAGNIFIER_KEYS:
            self._update_axis_priority_on_press(viewport, key)
        self.handler.store.emit_viewport_change("interaction")

    def handle_key_release(self, event) -> None:
        key = event.key()
        viewport = self.handler.store.viewport
        if key == Qt.Key.Key_Space:
            if event.isAutoRepeat():
                return
            self.handler.preview.log_preview_debug("space_released")
            self.handler.preview.restore()
            viewport.interaction_state.space_bar_pressed = False
            self.handler.store.emit_viewport_change("interaction")
            event.accept()
            return

        if key in self.MAGNIFIER_KEYS and event.isAutoRepeat():
            event.accept()
            return

        if key == Qt.Key.Key_Shift and self.handler.preview.is_active:
            self.handler.preview.log_preview_debug(
                "shift_released_restores_shift_preview"
            )
            self.handler.preview.restore()
            event.accept()
            return

        viewport.interaction_state.pressed_keys.discard(key)
        if key in self.MAGNIFIER_KEYS:
            self._update_axis_priority_on_release(viewport, key)
        self.handler.store.emit_viewport_change("interaction")
        if (
            viewport.view_state.use_magnifier
            and not any(k in viewport.interaction_state.pressed_keys for k in self.MAGNIFIER_KEYS)
            and not (
                viewport.interaction_state.is_dragging_split_line
                or viewport.interaction_state.is_dragging_capture_point
                or viewport.interaction_state.is_dragging_split_in_magnifier
                or viewport.interaction_state.is_dragging_any_slider
            )
            and self.handler.main_controller
        ):
            self.handler.main_controller.stop_interactive_movement.emit()
