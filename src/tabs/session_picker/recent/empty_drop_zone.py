"""Empty-state drop target for the Session Picker Recent shelf."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from tabs.session_picker.recent.layout import EMPTY_DROP_ZONE_H, PANEL_RADIUS


class EmptyDropZone(QWidget):
    """Dashed DnD placeholder shown when Recent has no pinned projects."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = ""
        self._hint = ""
        self._drag_active = False
        self._border = QColor(120, 120, 120)
        self._title_color = QColor(40, 40, 40)
        self._hint_color = QColor(90, 90, 90)
        self._fill = QColor(0, 0, 0, 0)
        self.setObjectName("RecentEmptyDropZone")
        self.setAcceptDrops(True)
        self.setFixedHeight(EMPTY_DROP_ZONE_H)
        self.setMinimumHeight(EMPTY_DROP_ZONE_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAutoFillBackground(False)

    def set_texts(self, *, title: str, hint: str) -> None:
        self._title = str(title or "")
        self._hint = str(hint or "")
        self.update()

    def set_drag_active(self, active: bool) -> None:
        active = bool(active)
        if self._drag_active == active:
            return
        self._drag_active = active
        self.update()

    def set_palette_colors(
        self,
        *,
        border: QColor,
        title: QColor,
        hint: QColor,
        fill: QColor | None = None,
    ) -> None:
        self._border = QColor(border)
        self._title_color = QColor(title)
        self._hint_color = QColor(hint)
        if fill is not None:
            self._fill = QColor(fill)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(1, 1, -2, -2)
        path = QPainterPath()
        path.addRoundedRect(rect, PANEL_RADIUS - 2, PANEL_RADIUS - 2)

        if self._fill.alpha() > 0:
            painter.fillPath(path, self._fill)

        pen = QPen(self._border, 1.6 if self._drag_active else 1.25)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setDashPattern([5.0, 4.0])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        mid_y = rect.center().y()
        title_font = QFont(painter.font())
        title_font.setPixelSize(14)
        title_font.setBold(True)
        hint_font = QFont(painter.font())
        hint_font.setPixelSize(12)

        title_fm = QFontMetrics(title_font)
        hint_fm = QFontMetrics(hint_font)
        gap = 6
        block_h = title_fm.height()
        if self._hint:
            block_h += gap + hint_fm.height()
        top = mid_y - block_h / 2.0

        if self._title:
            painter.setFont(title_font)
            painter.setPen(self._title_color)
            painter.drawText(
                int(rect.left() + 16),
                int(top),
                int(rect.width() - 32),
                title_fm.height(),
                int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
                self._title,
            )
            top += title_fm.height() + gap

        if self._hint:
            painter.setFont(hint_font)
            painter.setPen(self._hint_color)
            painter.drawText(
                int(rect.left() + 16),
                int(top),
                int(rect.width() - 32),
                hint_fm.height(),
                int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
                self._hint,
            )

        painter.end()
