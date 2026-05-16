from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor

@dataclass(frozen=True)
class WidgetStyleTokens:
    variant: str = "default"
    tone: str = "neutral"
    density: str = "normal"
    shape: str = "rounded"
    accent_color: QColor | None = None
    background_color: QColor | None = None
    foreground_color: QColor | None = None
    underline_color: QColor | None = None
    icon_size_px: int | None = None
    corner_radius_px: int | None = None
    show_underline: bool | None = None

def _as_str(value, default: str) -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default

def _as_int(value, default: int | None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def _as_bool(value, default: bool | None) -> bool | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)

def _as_color(value) -> QColor | None:
    if value is None:
        return None
    if isinstance(value, QColor):
        return QColor(value)
    try:
        color = QColor(value)
    except Exception:
        return None
    return color if color.isValid() else None

def read_widget_style(
    widget,
    *,
    default_icon_size: int = 22,
    default_corner_radius: int = 6,
) -> WidgetStyleTokens:
    foreground = _as_color(
        widget.property("foregroundColor") if widget is not None else None
    )
    if foreground is None:
        foreground = _as_color(
            widget.property("textColor") if widget is not None else None
        )
    return WidgetStyleTokens(
        variant=_as_str(
            widget.property("variant") if widget is not None else None, "default"
        ),
        tone=_as_str(widget.property("tone") if widget is not None else None, "neutral"),
        density=_as_str(
            widget.property("density") if widget is not None else None, "normal"
        ),
        shape=_as_str(
            widget.property("shape") if widget is not None else None, "rounded"
        ),
        accent_color=_as_color(
            widget.property("accentColor") if widget is not None else None
        ),
        background_color=_as_color(
            widget.property("backgroundColor") if widget is not None else None
        ),
        foreground_color=foreground,
        underline_color=_as_color(
            widget.property("underlineColor") if widget is not None else None
        ),
        icon_size_px=_as_int(
            widget.property("iconSizePx") if widget is not None else None,
            default_icon_size,
        ),
        corner_radius_px=_as_int(
            widget.property("cornerRadiusPx") if widget is not None else None,
            default_corner_radius,
        ),
        show_underline=_as_bool(
            widget.property("showUnderline") if widget is not None else None, None
        ),
    )

def update_widget_style(widget, *, update_geometry: bool = False) -> None:
    if widget is None:
        return
    if getattr(widget, "_sli_style_refreshing", False):
        if update_geometry:
            widget.updateGeometry()
        widget.update()
        return
    widget._sli_style_refreshing = True
    try:
        style = widget.style()
        if style is not None:
            style.unpolish(widget)
            style.polish(widget)
        if update_geometry:
            widget.updateGeometry()
        widget.update()
    finally:
        widget._sli_style_refreshing = False

def icon_size_qsize(px: int | None, fallback: int = 22) -> QSize:
    size = max(1, int(px or fallback))
    return QSize(size, size)
