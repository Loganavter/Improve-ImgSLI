from PyQt6.QtCore import QPoint, QPointF, QRect
from PyQt6.QtGui import QColor

from domain.types import Color, Point, Rect

def point_to_qpointf(p: Point) -> QPointF:
    return QPointF(p.x, p.y)

def qpointf_to_point(q: QPointF) -> Point:
    return Point(q.x(), q.y())

def point_to_qpoint(p: Point) -> QPoint:
    return QPoint(int(p.x), int(p.y))

def qpoint_to_point(q: QPoint) -> Point:
    return Point(float(q.x()), float(q.y()))

def color_to_qcolor(c: Color | QColor) -> QColor:
    if isinstance(c, QColor):
        return QColor(c)
    return QColor(c.r, c.g, c.b, c.a)

def qcolor_to_color(q: QColor) -> Color:
    return Color(q.red(), q.green(), q.blue(), q.alpha())

def rect_to_qrect(r: Rect) -> QRect:
    return QRect(r.x, r.y, r.w, r.h)

def qrect_to_rect(q: QRect) -> Rect:
    return Rect(q.x(), q.y(), q.width(), q.height())

def hex_to_color(hex_str: str) -> Color:
    q = QColor(hex_str)
    return Color(q.red(), q.green(), q.blue(), q.alpha())

def color_to_hex(c: Color) -> str:
    return QColor(c.r, c.g, c.b, c.a).name(QColor.NameFormat.HexArgb)
