from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPalette

from ui.canvas_infra.viewport.state import (
    get_pan_offset_x,
    get_pan_offset_y,
    get_zoom_level,
)


def widget_px_to_screen_px(widget, px_x, px_y):
    w, h = widget.width(), widget.height()
    if w <= 0 or h <= 0:
        return px_x, px_y
    zoom = get_zoom_level(widget)
    pan_x = get_pan_offset_x(widget)
    pan_y = get_pan_offset_y(widget)

    sx = ((px_x / w) - 0.5 + pan_x) * zoom + 0.5
    sy = ((px_y / h) - 0.5 + pan_y) * zoom + 0.5
    return sx * w, sy * h


def resolve_widget_background(widget) -> QColor:
    """Return the effective background color for the QRhi clear color."""
    plan = getattr(widget, "_active_render_plan", None)
    fill_rgba = getattr(plan, "fill_rgba", None)
    if bool(getattr(widget, "_use_plan_fill_clear", False)) and fill_rgba is not None:
        r, g, b, a = fill_rgba
        return QColor(int(r), int(g), int(b), int(a))
    bg = getattr(widget, "_theme_background_color", None)
    if not isinstance(bg, QColor) or not bg.isValid():
        palette = widget.palette()
        bg = palette.color(QPalette.ColorRole.Window)
        if not bg.isValid():
            bg = palette.color(QPalette.ColorRole.Base)
        if not bg.isValid():
            bg = QColor(245, 245, 245)
    return bg


def should_render_blank_white(scene_frame) -> bool:
    return bool(getattr(scene_frame, "blank_white", False))


def new_overlay_image(width: int, height: int) -> QImage:
    image = QImage(width, height, QImage.Format.Format_RGBA8888_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    return image
