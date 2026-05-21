from dataclasses import dataclass
from typing import List, Optional, Union

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import QLineEdit

from sli_ui_toolkit.theme import ThemeManager

@dataclass
class UnderlineConfig:
    thickness: float = 0.15
    vertical_offset: float = 0.75
    arc_radius: float = 1.33
    alpha: Optional[int] = None
    color: Union[QColor, List[QColor], None] = None

def _widget_scale(rect) -> float:
    """Scale factor based on widget height (baseline: 32px button)."""
    h = float(rect.height())
    return max(1.0, h / 32.0)

def draw_bottom_underline(
    painter, rect, theme_manager: ThemeManager, config: UnderlineConfig | None = None
):
    cfg = config or UnderlineConfig()
    widget = painter.device()

    if theme_manager.is_dark():
        if not (widget and isinstance(widget, QLineEdit)):
            return

    if widget and hasattr(widget, "property"):
        btn_class = str(widget.property("class") or "")
        prefix = "button.primary" if btn_class == "primary" else "button.default"
    else:
        prefix = "button.default"

    if isinstance(cfg.color, list) and cfg.color:
        colors = cfg.color
    elif isinstance(cfg.color, QColor):
        colors = [cfg.color]
    else:
        colors = [QColor(theme_manager.get_color(f"{prefix}.bottom.edge"))]

    final_colors = []
    for color in colors:
        new_color = QColor(color)
        if cfg.alpha is not None:
            new_color.setAlpha(int(cfg.alpha))
        final_colors.append(new_color)

    count = len(final_colors)
    if count == 0:
        return

    scale = _widget_scale(rect)
    arc_radius = float(cfg.arc_radius) * scale
    thickness = cfg.thickness * scale
    vertical_offset = cfg.vertical_offset * scale
    base_y = float(rect.bottom()) - vertical_offset
    start_x = float(rect.left())
    end_x = float(rect.right())
    total_width = end_x - start_x
    segment_width = total_width / count

    for i, color in enumerate(final_colors):
        pen = QPen(color)
        pen.setWidthF(thickness)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)

        seg_start = start_x + (i * segment_width)
        seg_end = start_x + ((i + 1) * segment_width)
        line_start_x = seg_start + arc_radius if i == 0 else seg_start
        line_end_x = seg_end - arc_radius if i == count - 1 else seg_end

        if i == 0:
            left_rect = QRectF(
                start_x,
                base_y - 2 * arc_radius,
                2 * arc_radius,
                2 * arc_radius,
            )
            painter.drawArc(left_rect, 180 * 16, 90 * 16)

        if line_end_x > line_start_x:
            painter.drawLine(
                QPointF(line_start_x, base_y),
                QPointF(line_end_x, base_y),
            )

        if i == count - 1:
            right_rect = QRectF(
                end_x - 2 * arc_radius,
                base_y - 2 * arc_radius,
                2 * arc_radius,
                2 * arc_radius,
            )
            painter.drawArc(right_rect, 270 * 16, 90 * 16)

