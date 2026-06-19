from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget


class InspectorOverlay(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("UiInspectorOverlay")
        self.setProperty("_ui_inspector_owned", True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._target_rect = QRect()
        self._label = ""
        self.hide()

    def set_target(self, rect: QRect, label: str) -> None:
        self._target_rect = QRect(rect)
        self._label = label
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self.update()

    def clear_target(self) -> None:
        self._target_rect = QRect()
        self._label = ""
        self.update()

    def paintEvent(self, _event) -> None:
        if self._target_rect.isNull() or not self._target_rect.isValid():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(QPen(QColor("#ff2d7dff"), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self._target_rect.adjusted(1, 1, -2, -2))
        if self._label:
            self._draw_label(painter)

    def _draw_label(self, painter: QPainter) -> None:
        metrics = QFontMetrics(painter.font())
        padding_x = 8
        padding_y = 5
        label_width = metrics.horizontalAdvance(self._label) + padding_x * 2
        label_height = metrics.height() + padding_y * 2
        x = self._target_rect.left()
        y = self._target_rect.top() - label_height - 4
        if y < 4:
            y = self._target_rect.bottom() + 4
        x = max(4, min(x, self.width() - label_width - 4))
        y = max(4, min(y, self.height() - label_height - 4))
        box = QRect(x, y, label_width, label_height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(24, 24, 24, 230))
        painter.drawRoundedRect(box, 5, 5)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(
            box.adjusted(padding_x, padding_y, -padding_x, -padding_y),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._label,
        )

