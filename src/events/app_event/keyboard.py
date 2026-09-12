from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QTextEdit

from events.app_event.common import get_main_controller
from tabs.registry import get_shared_tab_registry

logger = logging.getLogger("ImproveImgSLI")

class GlobalKeyboardHandler:
    OVERLAY_MOVEMENT_KEYS = {
        Qt.Key.Key_Q,
        Qt.Key.Key_E,
        Qt.Key.Key_W,
        Qt.Key.Key_A,
        Qt.Key.Key_S,
        Qt.Key.Key_D,
    }

    def __init__(self, store, presenter_provider, movement_controller, keyboard_state):
        self.store = store
        self._presenter_provider = presenter_provider
        self._movement_controller = movement_controller
        self.keyboard_state = keyboard_state

    @property
    def presenter(self):
        return self._presenter_provider()

    @staticmethod
    def _should_log_suppressed_reason(reason: str) -> bool:
        return reason not in {
            "ignored_untracked",
            "overlay_auto_repeat",
            "space_auto_repeat",
            "stray_release",
            "space_stray_release",
        }

    def should_route_globally(self, event: QKeyEvent, watched_obj: QObject) -> bool:
        active_tab = get_shared_tab_registry().get_active_tab()
        if active_tab is not None and active_tab.owns_widget(watched_obj):
            return False

        focused_widget = QApplication.focusWidget()
        if active_tab is not None and active_tab.owns_widget(focused_widget):
            return False
        if isinstance(focused_widget, (QLineEdit, QTextEdit, QPlainTextEdit)):
            return False

        key = event.key()
        if key in self.OVERLAY_MOVEMENT_KEYS:
            return True
        if key == Qt.Key.Key_Space:
            return True
        if key == Qt.Key.Key_Shift and self.store.viewport.interaction_state.space_bar_pressed:
            return True
        return key in self.OVERLAY_MOVEMENT_KEYS

    def handle_key_press(self, event: QKeyEvent) -> None:
        key_code = event.key()
        is_overlay_key = key_code in self.OVERLAY_MOVEMENT_KEYS
        result = self.keyboard_state.press(key_code, is_auto_repeat=event.isAutoRepeat())
        if not result.applied:
            if not self._should_log_suppressed_reason(result.reason):
                return
            logger.warning(
                "Suppressed global key press: key=%s auto=%s reason=%s",
                int(key_code),
                bool(event.isAutoRepeat()),
                result.reason,
            )
            event.accept()
            return
        self.store.emit_viewport_change("interaction")

        self._movement_controller.start()

    def handle_key_release(self, event: QKeyEvent) -> None:
        key_code = event.key()
        result = self.keyboard_state.release(key_code, is_auto_repeat=event.isAutoRepeat())
        if not result.applied:
            if not self._should_log_suppressed_reason(result.reason):
                return
            logger.warning(
                "Suppressed global key release: key=%s auto=%s reason=%s",
                int(key_code),
                bool(event.isAutoRepeat()),
                result.reason,
            )
            event.accept()
            return
        self.store.emit_viewport_change("interaction")

        if (
            key_code in self.OVERLAY_MOVEMENT_KEYS
            and not self.keyboard_state.has_active_overlay_keys()
        ):
            self._movement_controller.stop()

        if key_code != Qt.Key.Key_Space:
            return

        if self.store.viewport.view_state.showing_single_image_mode == 0:
            return

        sessions = getattr(get_main_controller(self.presenter), "sessions", None)
        if sessions is not None:
            sessions.deactivate_single_image_mode()
