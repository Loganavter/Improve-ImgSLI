"""In-window drag ghost (host-owned; not part of sli-ui-toolkit)."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget


def make_count_slot_pixmap(template: QWidget, count: int) -> QPixmap:
    """Slot-shaped ghost with a centered count (multi-select drag)."""
    size = template.size()
    if size.width() < 8 or size.height() < 8:
        size = template.sizeHint()
    width = max(48, int(size.width()))
    height = max(28, int(size.height()))
    pixmap = QPixmap(QSize(width, height))
    pixmap.fill(Qt.GlobalColor.transparent)

    try:
        from sli_ui_toolkit.theme import ThemeManager

        from ui.theming import resolve_theme_color

        tm = ThemeManager.get_instance()
        fill = QColor(resolve_theme_color(tm, "list_item.background.hover"))
        accent = QColor(resolve_theme_color(tm, "accent"))
        text = QColor(resolve_theme_color(tm, "list_item.text.normal"))
    except Exception:
        fill = QColor(240, 240, 240)
        accent = QColor("#0078D4")
        text = QColor(30, 30, 30)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    rect = pixmap.rect().adjusted(2, 2, -2, -2)
    path = QPainterPath()
    path.addRoundedRect(rect, 8.0, 8.0)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(fill)
    painter.drawPath(path)

    pen = painter.pen()
    pen.setColor(accent)
    pen.setWidth(3)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    x = rect.left() + 3
    painter.drawLine(x, rect.top() + 7, x, rect.bottom() - 7)

    font = QFont(template.font())
    font.setBold(True)
    font.setPixelSize(16)
    painter.setFont(font)
    painter.setPen(text)
    painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), str(max(1, int(count))))
    painter.end()
    return pixmap


class DragGhostWidget(QWidget):
    def __init__(self, parent=None):
        if parent is None:
            raise ValueError("DragGhostWidget requires an in-window parent widget")
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Widget)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._pixmap = QPixmap()
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self.setOpacity(1.0)

    def set_pixmap(self, pixmap: QPixmap):
        self._pixmap = pixmap
        self.setFixedSize(pixmap.size())
        self.update()

    def setOpacity(self, opacity):
        self._opacity_effect.setOpacity(max(0.0, min(1.0, float(opacity))))

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
