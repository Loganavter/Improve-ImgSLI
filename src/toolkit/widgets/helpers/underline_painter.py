from dataclasses import dataclass, field
from PyQt6.QtCore import QRectF, QPointF, Qt
from PyQt6.QtGui import QPen, QColor
from PyQt6.QtWidgets import QLineEdit
from toolkit.managers.theme_manager import ThemeManager
from typing import Optional, List, Union

@dataclass
class UnderlineConfig:
    thickness: float = 0.15
    vertical_offset: float = 0.75
    arc_radius: float = 1.33
    alpha: Optional[int] = None
    color: Union[QColor, List[QColor], None] = None

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

    colors = []

    if isinstance(cfg.color, list) and cfg.color:
        colors = cfg.color
    elif isinstance(cfg.color, QColor):
        colors = [cfg.color]
    else:

        colors = [QColor(theme_manager.get_color(f"{prefix}.bottom.edge"))]

    final_colors = []
    for c in colors:
        new_c = QColor(c)
        if cfg.alpha is not None:
            new_c.setAlpha(int(cfg.alpha))
        final_colors.append(new_c)

    count = len(final_colors)
    if count == 0:
        return

    r = float(cfg.arc_radius)
    base_y = float(rect.bottom()) - cfg.vertical_offset
    start_x = float(rect.left())
    end_x = float(rect.right())
    total_width = end_x - start_x

    segment_width = total_width / count

    for i, color in enumerate(final_colors):
        pen = QPen(color)
        pen.setWidthF(cfg.thickness)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)

        seg_start = start_x + (i * segment_width)
        seg_end = start_x + ((i + 1) * segment_width)

        line_start_x = seg_start + r if i == 0 else seg_start

        line_end_x = seg_end - r if i == count - 1 else seg_end

        if i == 0:
            left_rect = QRectF(start_x, base_y - 2 * r, 2 * r, 2 * r)
            painter.drawArc(left_rect, 180 * 16, 90 * 16)

        if line_end_x > line_start_x:
            painter.drawLine(QPointF(line_start_x, base_y), QPointF(line_end_x, base_y))

        if i == count - 1:
            right_rect = QRectF(end_x - 2 * r, base_y - 2 * r, 2 * r, 2 * r)
            painter.drawArc(right_rect, 270 * 16, 90 * 16)

