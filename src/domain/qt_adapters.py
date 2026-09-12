from PySide6.QtGui import QColor

from domain.types import Color

# Toolbar / chrome underline defaults — never use fully transparent.
DEFAULT_VISIBLE_COLOR = Color(255, 255, 255, 255)


def color_to_qcolor(c: Color | QColor) -> QColor:
    if isinstance(c, QColor):
        return QColor(c)
    return QColor(c.r, c.g, c.b, c.a)


def qcolor_to_color(q: QColor) -> Color:
    return Color(q.red(), q.green(), q.blue(), q.alpha())


def ensure_visible_color(
    value: Color | QColor | tuple | list | None,
    *,
    fallback: Color = DEFAULT_VISIBLE_COLOR,
) -> Color:
    """Return a color with alpha > 0, else ``fallback`` (opaque white by default).

    Used for toolbar underlines and persisted chrome so a missing / zero-alpha
    value cannot make a control look "unset" or hide a canvas line.
    """
    if hasattr(value, "r") and hasattr(value, "g") and hasattr(value, "b"):
        if value is None:
            return fallback
        a = getattr(value, "a", 255)
        if int(a) <= 0:
            return fallback
        return Color(int(value.r), int(value.g), int(value.b), int(a))
    if isinstance(value, QColor):
        if not value.isValid() or value.alpha() <= 0:
            return fallback
        return Color(value.red(), value.green(), value.blue(), value.alpha())
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            r, g, b = int(value[0]), int(value[1]), int(value[2])
            a = int(value[3]) if len(value) > 3 else 255
        except (TypeError, ValueError):
            return fallback
        if a <= 0:
            return fallback
        return Color(r, g, b, a)
    return fallback


def ensure_visible_qcolor(
    value: Color | QColor | tuple | list | None,
    *,
    fallback: Color = DEFAULT_VISIBLE_COLOR,
) -> QColor:
    return color_to_qcolor(ensure_visible_color(value, fallback=fallback))


def hex_to_color(hex_str: str) -> Color:
    q = QColor(hex_str)
    return Color(q.red(), q.green(), q.blue(), q.alpha())


def color_to_hex(c: Color) -> str:
    return QColor(c.r, c.g, c.b, c.a).name(QColor.NameFormat.HexArgb)
