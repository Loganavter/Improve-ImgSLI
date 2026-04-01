import logging

from PyQt6.QtCore import QElapsedTimer, QObject, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent

from events.image_label import (
    ImageLabelGeometry,
    ImageLabelKeyboardHandler,
    ImageLabelMouseHandler,
    MagnifierPreviewController,
)

logger = logging.getLogger("ImproveImgSLI")

class ImageLabelEventHandler(QObject):
    def __init__(self, store, main_controller, parent=None):
        super().__init__(parent)
        self.store = store
        self.main_controller = main_controller
        self.presenter = parent

        self._mouse_move_timer = QElapsedTimer()
        self._mouse_move_timer.start()
        self.preview = MagnifierPreviewController(self)
        self.geometry = ImageLabelGeometry(self)
        self.mouse = ImageLabelMouseHandler(self)
        self.keyboard = ImageLabelKeyboardHandler(self)

    @property
    def event_bus(self):
        if self.main_controller is not None:
            return self.main_controller.event_bus
        return None

    def handle_mouse_press(self, event: QMouseEvent):
        self.mouse.handle_mouse_press(event)

    def handle_mouse_move(self, event: QMouseEvent):
        self.mouse.handle_mouse_move(event)

    def handle_mouse_release(self, event: QMouseEvent):
        self.mouse.handle_mouse_release(event)

    def handle_key_press(self, event: QKeyEvent):
        self.keyboard.handle_key_press(event)

    def handle_key_release(self, event: QKeyEvent):
        self.keyboard.handle_key_release(event)

    def handle_wheel_scroll(self, event: QWheelEvent):
        self.mouse.handle_wheel_scroll(event)
