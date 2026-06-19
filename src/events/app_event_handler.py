from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import (
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QKeyEvent,
    QMouseEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication
from events.app_event import (
    route_main_window_event,
)
from events.drag_drop_handler import DragAndDropService
from events.router import route_drag_and_drop_override, route_global_keyboard_event
from events.runtime import build_event_handler_runtime

import logging

logger = logging.getLogger("ImproveImgSLI")

class EventHandler(QObject):
    drag_enter_event_signal = Signal(QDragEnterEvent)
    drag_move_event_signal = Signal(QDragMoveEvent)
    drag_leave_event_signal = Signal(QEvent)
    drop_event_signal = Signal(QDropEvent)
    resize_event_signal = Signal(QEvent)
    close_event_signal = Signal(QEvent)
    mouse_press_event_signal = Signal(QMouseEvent)
    global_keyboard_press_event_signal = Signal(QKeyEvent)
    global_keyboard_release_event_signal = Signal(QKeyEvent)
    canvas_keyboard_press_event_signal = Signal(QKeyEvent)
    canvas_keyboard_release_event_signal = Signal(QKeyEvent)
    mouse_press_event_on_image_label_signal = Signal(QMouseEvent)
    mouse_move_event_on_image_label_signal = Signal(QMouseEvent)
    mouse_release_event_on_image_label_signal = Signal(QMouseEvent)
    mouse_wheel_event_on_image_label_signal = Signal(QWheelEvent)

    def __init__(self, store, presenter_ref):
        super().__init__()
        self.store = store
        self.presenter = presenter_ref
        self.runtime = build_event_handler_runtime(
            store,
            presenter_provider=lambda: self.presenter,
            parent=self,
        )
        self.interactive_movement = self.runtime.interactive_movement
        self.keyboard_handler = self.runtime.keyboard_handler
        self.keyboard_state = self.runtime.keyboard_state
        self.resize_timer = self.runtime.resize_timer
        self.resize_timer.timeout.connect(self._finish_resize)

        self.global_keyboard_press_event_signal.connect(self.handle_key_press)
        self.global_keyboard_release_event_signal.connect(self.handle_key_release)

    def eventFilter(self, watched_obj, event: QEvent) -> bool:
        event_type = event.type()

        dnd_service = DragAndDropService.get_instance()
        if route_drag_and_drop_override(self, event, dnd_service):
            return True

        if event_type == QEvent.Type.ApplicationDeactivate:
            self._reset_keyboard_state(f"event:{int(event_type)}")
        elif event_type == QEvent.Type.WindowDeactivate:
            app = QApplication.instance()
            active_window = app.activeWindow() if app is not None else None
            if watched_obj is self.presenter.main_window_app or watched_obj is active_window:
                self._reset_keyboard_state(f"event:{int(event_type)}")
        elif event_type == QEvent.Type.FocusOut:
            if watched_obj is self.presenter.main_window_app:
                self._reset_keyboard_state(f"event:{int(event_type)}")

        if event_type == QEvent.Type.MouseButtonPress:
            self.mouse_press_event_signal.emit(event)

        if route_global_keyboard_event(self, watched_obj, event):
            return True

        if route_main_window_event(self, watched_obj, event, dnd_service):
            return True

        return super().eventFilter(watched_obj, event)

    def start_interactive_movement(self):
        self.interactive_movement.start()

    def stop_interactive_movement(self):
        self.interactive_movement.stop()

    def handle_key_press(self, event: QKeyEvent):
        self.keyboard_handler.handle_key_press(event)

    def handle_key_release(self, event: QKeyEvent):
        self.keyboard_handler.handle_key_release(event)

    def _finish_resize(self):
        self.presenter.finish_resize_delay()

    def _reset_keyboard_state(self, reason: str) -> None:
        result = self.keyboard_state.reset()
        session_reset = False
        image_label_handler = getattr(self.presenter, "image_label_handler", None)
        if image_label_handler is not None:
            try:
                session_reset = image_label_handler.input_session.reset()
            except Exception:
                pass
        if not result.applied and not session_reset:
            return
        self.store.emit_viewport_change("interaction")
        if not session_reset:
            try:
                self.stop_interactive_movement()
            except Exception:
                pass
