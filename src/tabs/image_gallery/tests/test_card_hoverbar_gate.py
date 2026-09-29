"""Hover-bar mutual exclusion: selected (bg-locked) cards paint no hover bar.

Lane B (plan-gallery-marquee-inpaint-2026-09-29, phase B1): the selection
fill already signals selection, so the hover bar must be skipped when the
card is bg-locked. Offscreen pixel pin — drives ``_dots_overlay_painter``
directly with ``_hover_blue_bar`` set (offscreen grab cannot do live Enter).
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QBuffer, QIODevice, QRect
from PySide6.QtGui import QColor, QImage, QPainter

from tabs.image_gallery.ui.card.painters import _dots_overlay_painter

_W, _H = 250, 170


def _fake_widget(*, locked: bool, hover_bar: bool) -> SimpleNamespace:
    text_region = SimpleNamespace(
        id="text",
        weight=1.0,
        rows=[SimpleNamespace(size=12, weight="normal")],
    )
    art_region = SimpleNamespace(id="art", weight=1.0, rows=None)
    return SimpleNamespace(
        _gallery_badge=None,
        _gallery_badge_style=None,
        _gallery_dot_colors=[QColor(200, 0, 0), QColor(0, 180, 0), QColor(0, 0, 200)],
        _hover_blue_bar=hover_bar,
        regions=lambda: [art_region, text_region],
        getContentPadding=lambda: (0, 0, 0, 0),
        is_bg_locked=lambda: locked,
    )


def _paint(widget: SimpleNamespace) -> QImage:
    img = QImage(_W, _H, QImage.Format.Format_ARGB32)
    img.fill(QColor(255, 255, 255))
    ctx = SimpleNamespace(widget=widget, rect=QRect(0, 0, _W, _H))
    painter = QPainter(img)
    try:
        _dots_overlay_painter(painter, ctx, None)
    finally:
        painter.end()
    return img


def _png_bytes(img: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def _band_diffs(a: QImage, b: QImage) -> int:
    """Count differing pixels inside the bar band (x 8..242, y H-11..H-9)."""
    n = 0
    for y in range(_H - 11, _H - 8):
        for x in range(8, 243):
            if a.pixel(x, y) != b.pixel(x, y):
                n += 1
    return n


def test_locked_hover_paints_no_bar(qtbot) -> None:
    """Selected + hovered card is pixel-identical to selected + not hovered."""
    locked_hover = _paint(_fake_widget(locked=True, hover_bar=True))
    locked_plain = _paint(_fake_widget(locked=True, hover_bar=False))
    assert _png_bytes(locked_hover) == _png_bytes(locked_plain)


def test_unlocked_hover_still_paints_bar(qtbot) -> None:
    """Guard against vacuity: unlocked + hovered must show bar-band pixels."""
    unlocked_hover = _paint(_fake_widget(locked=False, hover_bar=True))
    unlocked_plain = _paint(_fake_widget(locked=False, hover_bar=False))
    assert _band_diffs(unlocked_hover, unlocked_plain) > 0
