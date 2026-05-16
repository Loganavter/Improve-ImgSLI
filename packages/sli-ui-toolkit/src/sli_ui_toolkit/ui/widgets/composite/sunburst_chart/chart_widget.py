from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QPointF
from PyQt6.QtGui import QBrush, QColor, QPainter, QFont
from PyQt6.QtWidgets import (
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from sli_ui_toolkit.ui.widgets.composite.sunburst_chart.models import SunburstSegmentData
from sli_ui_toolkit.ui.widgets.composite.sunburst_chart.segment_item import (
    SegmentSignals,
    SunburstSegmentItem,
)

class SunburstChartWidget(QWidget):
    """Generic sunburst/donut chart widget.

    Feed it a list of ``SunburstSegmentData`` via ``set_segments()``.
    Connect to signals for user interaction.
    """

    segment_clicked = pyqtSignal(str, int)
    segment_hover_enter = pyqtSignal(object, QPointF)
    segment_hover_move = pyqtSignal(object, QPointF)
    segment_hover_leave = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._bg_color = QColor(30, 30, 30)
        self._gap_color: QColor | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._scene = QGraphicsScene(self)
        self._view = QGraphicsView(self._scene)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._view.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self._view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.setFrameShape(QGraphicsView.Shape.NoFrame)
        self._view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._view.setMinimumSize(0, 0)
        layout.addWidget(self._view)

        self._signals = SegmentSignals()
        self._signals.clicked.connect(self.segment_clicked.emit)
        self._signals.hover_enter.connect(self.segment_hover_enter.emit)
        self._signals.hover_move.connect(self.segment_hover_move.emit)
        self._signals.hover_leave.connect(self.segment_hover_leave.emit)

    def set_background_color(self, color: QColor) -> None:
        self._bg_color = QColor(color)
        self._view.setBackgroundBrush(QBrush(self._bg_color))

    def set_gap_color(self, color: QColor) -> None:
        self._gap_color = QColor(color)

    def set_segments(
        self,
        segments: list[SunburstSegmentData],
        *,
        center_text: str = "",
        center_sub_text: str = "",
        center_font_scale: float = 1.0,
    ) -> None:
        self._scene.clear()
        self._view.setBackgroundBrush(QBrush(self._bg_color))

        for seg in segments:
            item = SunburstSegmentItem(seg, self._signals, gap_color=self._gap_color)
            self._scene.addItem(item)

        if center_text:
            self._draw_center_text(center_text, center_sub_text, center_font_scale)

        bounds = self._scene.itemsBoundingRect().adjusted(-10, -10, 10, 10)
        self._view.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)

    def clear(self) -> None:
        self._scene.clear()

    def fit_to_view(self) -> None:
        bounds = self._scene.itemsBoundingRect().adjusted(-10, -10, 10, 10)
        self._view.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._scene.items():
            self.fit_to_view()

    def _draw_center_text(
        self, text: str, sub_text: str, font_scale: float
    ) -> None:
        base_size = int(12 * font_scale)

        main_item = QGraphicsTextItem(text)
        font = QFont()
        font.setPointSize(base_size)
        font.setBold(True)
        main_item.setFont(font)
        main_item.setDefaultTextColor(QColor(255, 255, 255))
        br = main_item.boundingRect()
        main_item.setPos(-br.width() / 2, -br.height() / 2 - (6 if sub_text else 0))
        self._scene.addItem(main_item)

        if sub_text:
            sub_item = QGraphicsTextItem(sub_text)
            sub_font = QFont()
            sub_font.setPointSize(max(8, base_size - 3))
            sub_item.setFont(sub_font)
            sub_item.setDefaultTextColor(QColor(200, 200, 200))
            sbr = sub_item.boundingRect()
            sub_item.setPos(-sbr.width() / 2, br.height() / 2 - 4)
            self._scene.addItem(sub_item)

    @property
    def scene(self) -> QGraphicsScene:
        return self._scene

    @property
    def view(self) -> QGraphicsView:
        return self._view
