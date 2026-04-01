from PyQt6.QtCore import QEvent, QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QKeyEvent,
    QMouseEvent,
    QWheelEvent,
)
from events.app_event import (
    route_main_window_event,
)
from events.drag_drop_handler import DragAndDropService
from events.router import route_drag_and_drop_override, route_global_keyboard_event
from events.runtime import build_event_handler_runtime

class EventHandler(QObject):
    drag_enter_event_signal = pyqtSignal(QDragEnterEvent)
    drag_move_event_signal = pyqtSignal(QDragMoveEvent)
    drag_leave_event_signal = pyqtSignal(QEvent)
    drop_event_signal = pyqtSignal(QDropEvent)
    resize_event_signal = pyqtSignal(QEvent)
    close_event_signal = pyqtSignal(QEvent)
    mouse_press_event_signal = pyqtSignal(QMouseEvent)
    keyboard_press_event_signal = pyqtSignal(QKeyEvent)
    keyboard_release_event_signal = pyqtSignal(QKeyEvent)
    mouse_press_event_on_image_label_signal = pyqtSignal(QMouseEvent)
    mouse_move_event_on_image_label_signal = pyqtSignal(QMouseEvent)
    mouse_release_event_on_image_label_signal = pyqtSignal(QMouseEvent)
    mouse_wheel_event_on_image_label_signal = pyqtSignal(QWheelEvent)

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
        self.resize_timer = self.runtime.resize_timer
        self.resize_timer.timeout.connect(self._finish_resize)

        self.keyboard_press_event_signal.connect(self.handle_key_press)
        self.keyboard_release_event_signal.connect(self.handle_key_release)

    def eventFilter(self, watched_obj, event: QEvent) -> bool:
        event_type = event.type()

        dnd_service = DragAndDropService.get_instance()
        if route_drag_and_drop_override(self, event, dnd_service):
            return True

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
