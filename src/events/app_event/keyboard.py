from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QTextEdit

from plugins.export.events import ExportPasteImageFromClipboardEvent
from events.app_event.common import get_event_bus, get_main_controller

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

    @staticmethod
    def _is_same_widget_or_descendant(candidate: QObject | None, target: QObject | None) -> bool:
        current = candidate
        while current is not None:
            if current is target:
                return True
            current = current.parent()
        return False

    @classmethod
    def _belongs_to_canvas(cls, candidate: QObject | None, image_label: QObject | None) -> bool:
        if candidate is None or image_label is None:
            return False
        if cls._is_same_widget_or_descendant(candidate, image_label):
            return True
        for attr_name in ("_window_container", "_canvas_window"):
            owned = getattr(image_label, attr_name, None)
            if candidate is owned:
                return True
            if cls._is_same_widget_or_descendant(candidate, owned):
                return True
        return False

    def should_route_globally(self, event: QKeyEvent, watched_obj: QObject) -> bool:
        presenter = self.presenter
        if presenter is not None and hasattr(presenter, "ui") and presenter.ui is not None:
            image_label = getattr(presenter.ui, "image_label", None)
            if self._belongs_to_canvas(watched_obj, image_label):
                return False

        focused_widget = QApplication.focusWidget()
        if presenter is not None and hasattr(presenter, "ui") and presenter.ui is not None:
            image_label = getattr(presenter.ui, "image_label", None)
            if self._belongs_to_canvas(focused_widget, image_label):
                return False
        if isinstance(focused_widget, (QLineEdit, QTextEdit, QPlainTextEdit)):
            return False

        key = event.key()
        if key in self.OVERLAY_MOVEMENT_KEYS:
            return True
        modifiers = event.modifiers()
        if key == Qt.Key.Key_V and modifiers & Qt.KeyboardModifier.ControlModifier:
            return True
        if key == Qt.Key.Key_S and modifiers == Qt.KeyboardModifier.ControlModifier:
            return True
        if key == Qt.Key.Key_S and modifiers == (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
        ):
            return True
        if key == Qt.Key.Key_Space:
            return True
        if key == Qt.Key.Key_Shift and self.store.viewport.interaction_state.space_bar_pressed:
            return True
        return key in self.OVERLAY_MOVEMENT_KEYS

    def handle_key_press(self, event: QKeyEvent) -> None:
        key_code = event.key()
        modifiers = event.modifiers()
        if key_code == Qt.Key.Key_V and modifiers & Qt.KeyboardModifier.ControlModifier:
            event_bus = get_event_bus(self.presenter)
            if event_bus is not None:
                event_bus.emit(ExportPasteImageFromClipboardEvent())
            event.accept()
            return

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

        if (is_overlay_key and self.store.viewport.view_state.overlay_enabled) or not is_overlay_key:
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
            and self.store.viewport.view_state.overlay_enabled
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
