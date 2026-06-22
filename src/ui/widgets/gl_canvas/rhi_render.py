from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

from .rhi_renderer import RhiCanvasRenderer


def resolve_clear_color(widget) -> QColor:
    plan = getattr(widget, "_active_render_plan", None)
    fill_rgba = getattr(plan, "fill_rgba", None)
    if bool(getattr(widget, "_use_plan_fill_clear", False)) and fill_rgba is not None:
        return QColor(*fill_rgba)

    color = getattr(widget, "_theme_background_color", None)
    if isinstance(color, QColor) and color.isValid():
        return QColor(color)

    palette = widget.palette()
    color = palette.color(QPalette.ColorRole.Window)
    if not color.isValid():
        color = palette.color(QPalette.ColorRole.Base)
    if not color.isValid():
        color = QColor(245, 245, 245)
    color.setAlpha(255)
    return color


def render_clear_frame(widget, command_buffer) -> None:
    widget._rhi_renderer.render(widget, command_buffer, resolve_clear_color(widget))
