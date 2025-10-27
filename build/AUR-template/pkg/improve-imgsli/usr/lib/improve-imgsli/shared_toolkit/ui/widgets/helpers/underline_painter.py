from dataclasses import dataclass, field
from PyQt6.QtCore import QRectF, QPointF, Qt
from PyQt6.QtGui import QPen, QColor
from PyQt6.QtWidgets import QLineEdit
from shared_toolkit.ui.managers.theme_manager import ThemeManager
from typing import Optional

@dataclass
class UnderlineConfig:
    thickness: float = 0.15
    vertical_offset: float = 0.75
    arc_radius: float = 1.33
    alpha: Optional[int] = None
    color: Optional[QColor] = None

def draw_bottom_underline(painter, rect, theme_manager: ThemeManager, config: UnderlineConfig | None = None):
    cfg = config or UnderlineConfig()

    widget = painter.device()

    if theme_manager.is_dark():
        if not (widget and isinstance(widget, QLineEdit)):
            return

    prefix = ""
    if widget and hasattr(widget, 'property'):
        btn_class = str(widget.property("class") or "")
        prefix = "button.primary" if btn_class == "primary" else "button.default"
    else:

        prefix = "button.default"

    if config is not None and cfg.color is not None:
        edge = QColor(cfg.color)
    else:
        edge = QColor(theme_manager.get_color(f"{prefix}.bottom.edge"))

    if config is not None and cfg.alpha is not None:
        edge.setAlpha(int(cfg.alpha))

    pen_edge = QPen(edge)
    pen_edge.setWidthF(cfg.thickness)
    pen_edge.setCapStyle(Qt.PenCapStyle.FlatCap)

    painter.setPen(pen_edge)

    base_y = float(rect.bottom()) - cfg.vertical_offset
    r = float(cfg.arc_radius)
    left_x = float(rect.left())
    right_x = float(rect.right())

    painter.drawLine(QPointF(left_x + r, base_y), QPointF(right_x - r, base_y))

    left_rect = QRectF(left_x, base_y - 2 * r, 2 * r, 2 * r)
    painter.drawArc(left_rect, 180 * 16, 90 * 16)

    right_rect = QRectF(right_x - 2 * r, base_y - 2 * r, 2 * r, 2 * r)
    painter.drawArc(right_rect, 270 * 16, 90 * 16)
