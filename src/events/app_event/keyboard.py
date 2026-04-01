from __future__ import annotations

from PyQt6.QtCore import QObject, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QTextEdit

from core.events import ExportPasteImageFromClipboardEvent
from events.app_event.common import get_event_bus, get_main_controller

class GlobalKeyboardHandler:
    MAGNIFIER_KEYS = {
        Qt.Key.Key_Q,
        Qt.Key.Key_E,
        Qt.Key.Key_W,
        Qt.Key.Key_A,
        Qt.Key.Key_S,
        Qt.Key.Key_D,
    }

    def __init__(self, store, presenter_provider, movement_controller):
        self.store = store
        self._presenter_provider = presenter_provider
        self._movement_controller = movement_controller

    @staticmethod
    def _update_axis_priority_on_press(viewport, key_code: int) -> None:
        if key_code in (Qt.Key.Key_A, Qt.Key.Key_D):
            viewport.interaction_state.last_horizontal_movement_key = key_code
        elif key_code in (Qt.Key.Key_W, Qt.Key.Key_S):
            viewport.interaction_state.last_vertical_movement_key = key_code
        elif key_code in (Qt.Key.Key_Q, Qt.Key.Key_E):
            viewport.interaction_state.last_spacing_movement_key = key_code

    @staticmethod
    def _update_axis_priority_on_release(viewport, key_code: int) -> None:
        if key_code in (Qt.Key.Key_A, Qt.Key.Key_D):
            if viewport.interaction_state.last_horizontal_movement_key == key_code:
                opposite = Qt.Key.Key_D if key_code == Qt.Key.Key_A else Qt.Key.Key_A
                viewport.interaction_state.last_horizontal_movement_key = (
                    opposite if opposite in viewport.interaction_state.pressed_keys else None
                )
        elif key_code in (Qt.Key.Key_W, Qt.Key.Key_S):
            if viewport.interaction_state.last_vertical_movement_key == key_code:
                opposite = Qt.Key.Key_S if key_code == Qt.Key.Key_W else Qt.Key.Key_W
                viewport.interaction_state.last_vertical_movement_key = (
                    opposite if opposite in viewport.interaction_state.pressed_keys else None
                )
        elif key_code in (Qt.Key.Key_Q, Qt.Key.Key_E):
            if viewport.interaction_state.last_spacing_movement_key == key_code:
                opposite = Qt.Key.Key_E if key_code == Qt.Key.Key_Q else Qt.Key.Key_Q
                viewport.interaction_state.last_spacing_movement_key = (
                    opposite if opposite in viewport.interaction_state.pressed_keys else None
                )

    @property
    def presenter(self):
        return self._presenter_provider()

    def should_route_globally(self, event: QKeyEvent, watched_obj: QObject) -> bool:
        presenter = self.presenter
        if presenter is not None and hasattr(presenter, "ui") and presenter.ui is not None:
            image_label = getattr(presenter.ui, "image_label", None)
            if watched_obj is image_label:
                return False

        focused_widget = QApplication.focusWidget()
        if isinstance(focused_widget, (QLineEdit, QTextEdit, QPlainTextEdit)):
            return False

        key = event.key()
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
        return key in self.MAGNIFIER_KEYS

    def handle_key_press(self, event: QKeyEvent) -> None:
        key_code = event.key()
        modifiers = event.modifiers()
        if key_code == Qt.Key.Key_V and modifiers & Qt.KeyboardModifier.ControlModifier:
            event_bus = get_event_bus(self.presenter)
            if event_bus is not None:
                event_bus.emit(ExportPasteImageFromClipboardEvent())
            event.accept()
            return

        is_magnifier_key = key_code in self.MAGNIFIER_KEYS
        if is_magnifier_key and event.isAutoRepeat():
            event.accept()
            return
        self.store.viewport.interaction_state.pressed_keys.add(key_code)
        if is_magnifier_key:
            self._update_axis_priority_on_press(self.store.viewport, key_code)
        self.store.emit_viewport_change("interaction")

        if key_code == Qt.Key.Key_Space:
            if event.isAutoRepeat():
                return
            self.store.viewport.interaction_state.space_bar_pressed = True
            self.store.emit_viewport_change("interaction")

        if (is_magnifier_key and self.store.viewport.view_state.use_magnifier) or not is_magnifier_key:
            self._movement_controller.start()

    def handle_key_release(self, event: QKeyEvent) -> None:
        key_code = event.key()
        if key_code in self.MAGNIFIER_KEYS and event.isAutoRepeat():
            event.accept()
            return
        self.store.viewport.interaction_state.pressed_keys.discard(key_code)
        if key_code in self.MAGNIFIER_KEYS:
            self._update_axis_priority_on_release(self.store.viewport, key_code)
        self.store.emit_viewport_change("interaction")

        if key_code != Qt.Key.Key_Space:
            return
        if event.isAutoRepeat():
            return

        self.store.viewport.interaction_state.space_bar_pressed = False
        self.store.emit_viewport_change("interaction")

        if self.store.viewport.view_state.showing_single_image_mode == 0:
            return

        sessions = getattr(get_main_controller(self.presenter), "sessions", None)
        if sessions is not None:
            sessions.deactivate_single_image_mode()
