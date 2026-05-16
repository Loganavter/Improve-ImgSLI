from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget

class DragDropOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._horizontal = False
        self._texts = ("", "")
        self._target_rect = None

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.hide()

    def set_overlay_state(
        self,
        visible: bool,
        target_rect,
        horizontal: bool = False,
        text1: str = "",
        text2: str = "",
    ):
        if target_rect is None:
            self.hide()
            return

        target_rect = target_rect.adjusted(0, 0, 0, 0)
        state_changed = (
            self._horizontal != horizontal
            or self._texts != (text1, text2)
            or self.geometry() != target_rect
            or self.isVisible() != bool(visible)
        )

        self._horizontal = horizontal
        self._texts = (text1, text2)
        self._target_rect = target_rect
        self.setGeometry(target_rect)

        if visible:
            self.raise_()
            self.show()
        else:
            self.hide()

        if state_changed and visible:
            self.update()

    def paintEvent(self, event):
        if not self.isVisible():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        font = QFont(self.font())
        font.setPixelSize(20)
        font.setBold(True)
        painter.setFont(font)

        margin = 10.0
        half_margin = margin / 2.0
        width = float(self.width())
        height = float(self.height())

        if self._horizontal:
            half_height = height / 2.0
            rects = [
                QRectF(
                    margin,
                    margin,
                    max(1.0, width - 2.0 * margin),
                    max(1.0, half_height - margin - half_margin),
                ),
                QRectF(
                    margin,
                    half_height + half_margin,
                    max(1.0, width - 2.0 * margin),
                    max(1.0, half_height - margin - half_margin),
                ),
            ]
        else:
            half_width = width / 2.0
            rects = [
                QRectF(
                    margin,
                    margin,
                    max(1.0, half_width - margin - half_margin),
                    max(1.0, height - 2.0 * margin),
                ),
                QRectF(
                    half_width + half_margin,
                    margin,
                    max(1.0, half_width - margin - half_margin),
                    max(1.0, height - 2.0 * margin),
                ),
            ]

        fill = QColor(0, 100, 200, 153)
        border = QColor(255, 255, 255, 179)
        pen = QPen(border, 1.25)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(fill)

        for rect, text in zip(rects, self._texts):
            path = QPainterPath()
            path.addRoundedRect(rect, 10.0, 10.0)
            painter.drawPath(path)
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(
                rect.adjusted(15.0, 15.0, -15.0, -15.0),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                text,
            )
            painter.setPen(pen)
