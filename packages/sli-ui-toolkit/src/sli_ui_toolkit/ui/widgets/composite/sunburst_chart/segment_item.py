from __future__ import annotations

import math

from PyQt6.QtCore import QObject, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QPainterPath, QPen
from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsTextItem

from sli_ui_toolkit.ui.widgets.composite.sunburst_chart.models import SunburstSegmentData

class SegmentSignals(QObject):
    clicked = pyqtSignal(str, int)
    hover_enter = pyqtSignal(object, QPointF)
    hover_move = pyqtSignal(object, QPointF)
    hover_leave = pyqtSignal()

class SunburstSegmentItem(QGraphicsPathItem):
    SCENE_SCALE = 400.0

    def __init__(
        self,
        data: SunburstSegmentData,
        signals: SegmentSignals,
        *,
        gap_color: QColor | None = None,
    ):
        super().__init__()
        self.data = data
        self.signals = signals

        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable, False)

        self._update_path()
        self._setup_appearance(gap_color)

        if data.label and data.font_size > 0:
            self._add_label()

    def _update_path(self):
        path = QPainterPath()

        inner_r = self.data.inner_radius * self.SCENE_SCALE
        outer_r = self.data.outer_radius * self.SCENE_SCALE

        start_deg = math.degrees(self.data.start_angle)
        end_deg = math.degrees(self.data.end_angle)
        sweep = end_deg - start_deg

        outer_rect = QRectF(-outer_r, -outer_r, outer_r * 2, outer_r * 2)
        inner_rect = QRectF(-inner_r, -inner_r, inner_r * 2, inner_r * 2)

        path.arcMoveTo(outer_rect, start_deg)
        path.arcTo(outer_rect, start_deg, sweep)
        path.arcTo(inner_rect, start_deg + sweep, -sweep)
        path.closeSubpath()
        self.setPath(path)

    def _setup_appearance(self, gap_color: QColor | None):
        self.base_color = QColor(self.data.color)
        self.setBrush(QBrush(self.base_color))
        sweep_rad = self.data.end_angle - self.data.start_angle
        if sweep_rad >= 2.0 * math.pi - 0.01:
            self.setPen(QPen(Qt.PenStyle.NoPen))
        else:
            pen_color = gap_color if gap_color is not None else QColor(30, 30, 30)
            self.setPen(QPen(pen_color, 1.0, Qt.PenStyle.SolidLine))

    def _add_label(self):
        text_item = QGraphicsTextItem(self.data.label, self)
        font = QFont()
        font.setPointSize(int(self.data.font_size * 1.5))
        text_item.setFont(font)
        text_item.setDefaultTextColor(QColor(255, 255, 255))
        br = text_item.boundingRect()
        text_item.setTransformOriginPoint(br.width() / 2, br.height() / 2)

        mid_angle = (self.data.start_angle + self.data.end_angle) / 2.0
        center_r = (self.data.inner_radius + self.data.outer_radius) / 2.0
        label_x = center_r * math.cos(mid_angle) * self.SCENE_SCALE
        label_y = center_r * math.sin(mid_angle) * self.SCENE_SCALE

        text_item.setPos(label_x - br.width() / 2, -label_y - br.height() / 2)

        rotation_deg = math.degrees(mid_angle)
        if 90 < rotation_deg < 270:
            rotation_deg -= 180
        text_item.setRotation(-rotation_deg)
        text_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        text_item.setAcceptHoverEvents(False)

    def hoverEnterEvent(self, event):
        self.setBrush(QBrush(self.base_color.lighter(115)))
        self.signals.hover_enter.emit(self.data, QPointF(event.screenPos()))
        super().hoverEnterEvent(event)

    def hoverMoveEvent(self, event):
        self.signals.hover_move.emit(self.data, QPointF(event.screenPos()))
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QBrush(self.base_color))
        self.signals.hover_leave.emit()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.signals.clicked.emit(self.data.node_id, 1)
        elif event.button() == Qt.MouseButton.RightButton:
            self.signals.clicked.emit(self.data.node_id, 3)
        event.accept()
