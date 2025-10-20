from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import QLabel

class ClickableLabel(QLabel):
    mousePressed = pyqtSignal(QMouseEvent)
    mouseMoved = pyqtSignal(QMouseEvent)
    mouseReleased = pyqtSignal(QMouseEvent)
    keyPressed = pyqtSignal(QKeyEvent)
    keyReleased = pyqtSignal(QKeyEvent)
    wheelScrolled = pyqtSignal(QWheelEvent)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def mousePressEvent(self, event: QMouseEvent):
        self.mousePressed.emit(event)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        self.mouseMoved.emit(event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.mouseReleased.emit(event)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        self.keyPressed.emit(event)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        self.keyReleased.emit(event)
        super().keyReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        self.wheelScrolled.emit(event)
        event.accept()
