from __future__ import annotations

import logging

from PyQt6.QtCore import Qt

from events.canvas_input.owner_ids import KEYBOARD_MOVE_OWNER
from plugins.export.events import ExportPasteImageFromClipboardEvent

logger = logging.getLogger("ImproveImgSLI")

class ImageLabelKeyboardHandler:
    OVERLAY_MOVEMENT_KEYS = {
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
    def _should_log_suppressed_reason(reason: str) -> bool:
        return reason not in {
            "ignored_untracked",
            "overlay_auto_repeat",
            "space_auto_repeat",
            "stray_release",
            "space_stray_release",
        }

    def handle_key_press(self, event) -> None:
        key = event.key()
        viewport = self.handler.store.viewport
        keyboard_state = self.handler.keyboard_state_service
        if keyboard_state is None:
            logger.warning("Canvas keyboard state service is not configured")
            return
        if key == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            event_bus = self.handler.event_bus
            if event_bus is not None:
                event_bus.emit(ExportPasteImageFromClipboardEvent())
            event.accept()
            return
        result = keyboard_state.press(key, is_auto_repeat=event.isAutoRepeat())
        if not result.applied:
            if not self._should_log_suppressed_reason(result.reason):
                return
            logger.warning(
                "Suppressed canvas key press: key=%s auto=%s reason=%s",
                int(key),
                bool(event.isAutoRepeat()),
                result.reason,
            )
            event.accept()
            return
        if key == Qt.Key.Key_Space:
            self.handler.store.emit_viewport_change("interaction")
            self.handler.preview.log_preview_debug("space_pressed")
            event.accept()
            return

        if key == Qt.Key.Key_Shift and self.handler.preview.is_active:
            self.handler.preview.log_preview_debug("shift_pressed_during_shift_preview")
            event.accept()
            return

        if key in self.OVERLAY_MOVEMENT_KEYS:
            self.handler.input_session.activate(KEYBOARD_MOVE_OWNER)

        self.handler.store.emit_viewport_change("interaction")

    def handle_key_release(self, event) -> None:
        key = event.key()
        viewport = self.handler.store.viewport
        keyboard_state = self.handler.keyboard_state_service
        if keyboard_state is None:
            logger.warning("Canvas keyboard state service is not configured")
            return
        result = keyboard_state.release(key, is_auto_repeat=event.isAutoRepeat())
        if not result.applied:
            if not self._should_log_suppressed_reason(result.reason):
                return
            logger.warning(
                "Suppressed canvas key release: key=%s auto=%s reason=%s",
                int(key),
                bool(event.isAutoRepeat()),
                result.reason,
            )
            event.accept()
            return
        if key == Qt.Key.Key_Space:
            self.handler.preview.log_preview_debug("space_released")
            self.handler.preview.restore()
            if viewport.view_state.showing_single_image_mode != 0:
                if (
                    self.handler.main_controller is not None
                    and self.handler.main_controller.sessions is not None
                ):
                    self.handler.main_controller.sessions.deactivate_single_image_mode()
            self.handler.store.emit_viewport_change("interaction")
            event.accept()
            return

        if key == Qt.Key.Key_Shift and self.handler.preview.is_active:
            self.handler.preview.log_preview_debug(
                "shift_released_restores_shift_preview"
            )
            self.handler.preview.restore()
            event.accept()
            return

        self.handler.store.emit_viewport_change("interaction")
        if key in self.OVERLAY_MOVEMENT_KEYS and not keyboard_state.has_active_overlay_keys():
            self.handler.input_session.deactivate(KEYBOARD_MOVE_OWNER)
