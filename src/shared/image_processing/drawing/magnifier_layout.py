from PyQt6.QtCore import QPoint

def set_magnifier_combined_mode(store, combined: bool):
    try:
        store.viewport.view_state.is_magnifier_combined = combined
    except Exception:
        pass

def compute_axis_pair_centers(
    midpoint: QPoint, offset: float, layout_horizontal: bool
) -> tuple[QPoint, QPoint]:
    mid_x, mid_y = midpoint.x(), midpoint.y()
    if not layout_horizontal:
        return (
            QPoint(int(round(mid_x - offset)), int(round(mid_y))),
            QPoint(int(round(mid_x + offset)), int(round(mid_y))),
        )
    return (
        QPoint(int(round(mid_x)), int(round(mid_y - offset))),
        QPoint(int(round(mid_x)), int(round(mid_y + offset))),
    )

def compute_three_magnifier_side_centers(
    *,
    midpoint: QPoint,
    magnifier_size: int,
    spacing: int,
    layout_horizontal: bool,
) -> tuple[QPoint, QPoint]:
    offset = max(magnifier_size, magnifier_size + float(spacing))
    return compute_axis_pair_centers(midpoint, offset, layout_horizontal)

def compute_two_magnifier_centers(
    *,
    midpoint: QPoint,
    magnifier_size: int,
    spacing: int,
    layout_horizontal: bool,
) -> tuple[QPoint, QPoint]:
    radius = float(magnifier_size) / 2.0
    half_spacing = float(spacing) / 2.0
    return compute_axis_pair_centers(midpoint, radius + half_spacing, layout_horizontal)

def compute_diff_combined_position(
    *, midpoint: QPoint, magnifier_size: int, layout_horizontal: bool
) -> QPoint:
    mid_x, mid_y = midpoint.x(), midpoint.y()
    offset = magnifier_size + 8
    if not layout_horizontal:
        return QPoint(int(round(mid_x)), int(round(mid_y + offset)))
    return QPoint(int(round(mid_x + offset)), int(round(mid_y)))

def get_magnifier_sizes(magnifier_size_pixels: int) -> tuple[int, int]:
    border_width = max(2, int(magnifier_size_pixels * 0.015))
    return border_width, magnifier_size_pixels - border_width * 2 + 2
