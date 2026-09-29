"""Tests for ui.widgets.drag_ghost_service.GhostService (unified ghost)."""

from PySide6.QtCore import QPoint, QPointF
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget

from ui.widgets.drag_ghost_service import (
    GhostService,
    hotspot_center,
    hotspot_top_right,
)


def _pixmap(w=120, h=80):
    pix = QPixmap(w, h)
    pix.fill(0x112233)
    return pix


def test_hotspot_helpers_math(qapp):
    pix = _pixmap(120, 80)
    top_right = hotspot_top_right(pix)
    assert top_right.x() == 108 and top_right.y() == 12  # w-inset, inset
    center = hotspot_center(pix)
    assert center.x() == 60 and center.y() == 40


def test_show_rejects_null_pixmap(qapp):
    svc = GhostService()
    assert svc.show(QPixmap(), QPoint(100, 100), anchor=QWidget()) is False
    assert svc.is_showing is False


def test_show_rejects_missing_anchor(qapp):
    svc = GhostService()
    assert svc.show(_pixmap(), QPoint(100, 100), anchor=None) is False
    assert svc.is_showing is False


def _child_host():
    """Production-like host: a plain child widget (no top-level frame offset)."""
    window = QWidget()
    window.resize(800, 600)
    window.show()
    host = QWidget(window)
    host.setGeometry(0, 0, 800, 600)
    host.show()
    return window, host


def test_show_move_hide_lifecycle(qapp):
    window, host = _child_host()
    svc = GhostService(opacity=0.85)
    hotspot = QPointF(108, 12)
    assert svc.show(_pixmap(), QPoint(400, 300), anchor=host, hotspot=hotspot) is True
    assert svc.is_showing is True
    widget = svc._widget

    def _expect(global_pt):
        # Offscreen QPA may offset top-level windows; derive the expectation
        # through the same global->parent mapping production uses.
        return host.mapFromGlobal(global_pt) - hotspot.toPoint()

    assert widget.pos() == _expect(QPoint(400, 300))  # global minus hotspot
    svc.move(QPoint(500, 400))
    assert widget.pos() == _expect(QPoint(500, 400))
    svc.move(QPointF(520.9, 430.9))  # QPointF accepted too (Qt rounds)
    assert widget.pos() == _expect(QPoint(521, 431))
    svc.hide()
    assert svc.is_showing is False
    svc.hide()  # idempotent
    svc.move(QPoint(0, 0))  # no-op when hidden, never raises
    window.deleteLater()


def test_default_hotspot_is_carry_top_right(qapp):
    window, host = _child_host()
    svc = GhostService()
    assert svc.show(_pixmap(120, 80), QPoint(400, 300), anchor=host) is True
    assert svc._widget.pos() == host.mapFromGlobal(QPoint(400, 300)) - QPoint(108, 12)
    svc.hide()
    window.deleteLater()
