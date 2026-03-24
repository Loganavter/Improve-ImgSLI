from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, QSize
from PyQt6.QtWidgets import QWidget

def calculate_centered_overlay_geometry(
    *,
    anchor_widget: QWidget,
    owner_window: QWidget,
    content_size: QSize,
    shadow_radius: int,
    current_index: int,
    visible_index: int,
    row_height: int,
    scrollable: bool,
) -> QRect:
    outer_width = content_size.width() + shadow_radius * 2
    outer_height = content_size.height() + shadow_radius * 2

    combo_rect = anchor_widget.rect()
    anchor_center = anchor_widget.mapToGlobal(combo_rect.center())
    owner_top_left_global = anchor_widget.mapToGlobal(combo_rect.topLeft())
    window_top_left_global = owner_window.mapToGlobal(QPoint(0, 0))
    window_global_rect = QRect(window_top_left_global, owner_window.size())

    if current_index < 0:
        current_index = 0
    if visible_index < 0:
        visible_index = 0

    if scrollable:
        ideal_y_global = int(anchor_center.y() - outer_height / 2)
    else:
        selected_item_offset_y = visible_index * row_height
        ideal_y_global = int(
            anchor_center.y() - selected_item_offset_y - row_height / 2 - shadow_radius
        )

    ideal_x_global = int(owner_top_left_global.x() - shadow_radius)

    final_x_global = max(
        window_global_rect.left(),
        min(ideal_x_global, window_global_rect.right() - outer_width + 1),
    )
    final_y_global = max(
        window_global_rect.top(),
        min(ideal_y_global, window_global_rect.bottom() - outer_height + 1),
    )

    top_left = owner_window.mapFromGlobal(QPoint(final_x_global, final_y_global))
    return QRect(top_left.x(), top_left.y(), outer_width, outer_height)
