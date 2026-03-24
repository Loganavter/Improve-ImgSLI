from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter

def draw_rounded_shadow(
    painter: QPainter,
    rect: QRectF,
    *,
    steps: int,
    radius: float,
    alpha_max: int = 34,
) -> None:
    painter.setPen(Qt.PenStyle.NoPen)
    for i in range(steps):
        alpha = int(alpha_max * (1 - i / steps) ** 2)
        painter.setBrush(QColor(0, 0, 0, alpha))
        shadow_rect = QRectF(rect).adjusted(-i, -i + 1, i, i + 1)
        painter.drawRoundedRect(shadow_rect, radius + i, radius + i)
