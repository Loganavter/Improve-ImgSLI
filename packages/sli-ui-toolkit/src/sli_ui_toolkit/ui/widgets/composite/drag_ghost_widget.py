from PyQt6.QtCore import QPoint, QRectF, Qt
from PyQt6.QtGui import QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import QWidget

class DragGhostWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._pixmap = QPixmap()

        self.setOpacity(1.0)

    def set_pixmap(self, pixmap: QPixmap):
        self._pixmap = pixmap
        self.setFixedSize(pixmap.size())
        self.update()

    def setOpacity(self, opacity):
        self.setWindowOpacity(opacity)

    def move(self, pos):
        if isinstance(pos, QPoint) and self.parentWidget() is not None:
            return super().move(self.parentWidget().mapFromGlobal(pos))
        return super().move(pos)

    def paintEvent(self, event):
        if self._pixmap.isNull():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        rect = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(rect, 8.0, 8.0)
        painter.setClipPath(path)
        painter.drawPixmap(self.rect(), self._pixmap)
