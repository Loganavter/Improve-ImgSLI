"""Visible chrome colors never fall back to fully transparent."""

from domain.qt_adapters import (
    DEFAULT_VISIBLE_COLOR,
    ensure_visible_color,
    ensure_visible_qcolor,
)
from domain.types import Color
from PySide6.QtGui import QColor


def test_ensure_visible_color_rejects_zero_alpha():
    assert ensure_visible_color(Color(10, 20, 30, 0)) == DEFAULT_VISIBLE_COLOR
    assert ensure_visible_color((1, 2, 3, 0)) == DEFAULT_VISIBLE_COLOR
    assert ensure_visible_color(None) == DEFAULT_VISIBLE_COLOR
    assert ensure_visible_color(QColor(0, 0, 0, 0)) == DEFAULT_VISIBLE_COLOR


def test_ensure_visible_color_keeps_opaque():
    c = ensure_visible_color(Color(10, 20, 30, 200))
    assert (c.r, c.g, c.b, c.a) == (10, 20, 30, 200)


def test_ensure_visible_qcolor_custom_fallback():
    q = ensure_visible_qcolor(
        Color(0, 0, 0, 0), fallback=Color(9, 8, 7, 255)
    )
    assert (q.red(), q.green(), q.blue(), q.alpha()) == (9, 8, 7, 255)
