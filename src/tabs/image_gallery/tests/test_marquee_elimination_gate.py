"""Elimination gate for the host-click hover-loss bisect.

IMGSLI_GALLERY_NO_MARQUEE=1 must make empty-host presses fall through
(no gesture, no preview, no commit). If the hover-loss pattern disappears
with the gate on, the breakage lives somewhere in the marquee chain;
if it persists, the chain is innocent.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from tabs.image_gallery.ui import marquee as _marquee


def _press_at(host, local: QPoint) -> QMouseEvent:
    gp = host.mapToGlobal(local)
    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(local),
        QPointF(gp),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def test_gate_on_skips_gesture(qtbot, monkeypatch) -> None:
    from tabs.image_gallery.ui.grid_view import GalleryGridView

    monkeypatch.setenv("IMGSLI_GALLERY_NO_MARQUEE", "1")
    assert _marquee.marquee_disabled() is True
    view = GalleryGridView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.show()
    qtbot.wait(50)
    host = view.items_host
    empty = QPoint(host.width() - 30, host.height() - 30)
    assert _marquee.host_mouse_press(view, _press_at(host, empty)) is False
    assert view._marquee_gesture is None


def test_gate_off_starts_gesture(qtbot, monkeypatch) -> None:
    from tabs.image_gallery.ui.grid_view import GalleryGridView

    monkeypatch.delenv("IMGSLI_GALLERY_NO_MARQUEE", raising=False)
    assert _marquee.marquee_disabled() is False
    view = GalleryGridView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.show()
    qtbot.wait(50)
    host = view.items_host
    empty = QPoint(host.width() - 30, host.height() - 30)
    assert host.childAt(empty) is None
    assert _marquee.host_mouse_press(view, _press_at(host, empty)) is True
    assert view._marquee_gesture is not None


def test_commit_gate_skips_commit(qtbot, monkeypatch) -> None:
    from types import SimpleNamespace

    from PySide6.QtCore import QRect

    applied: list = []
    view = SimpleNamespace(
        _marquee_additive=False,
        _owner=None,
        _marquee_base=set(),
        apply_selection=lambda paths: applied.append(set(paths)),
    )
    monkeypatch.setenv("IMGSLI_GALLERY_NO_MARQUEE_COMMIT", "1")
    _marquee.on_rect_finish(view, QRect())
    assert applied == []


def test_commit_gate_off_clears_preview(qtbot, monkeypatch) -> None:
    from types import SimpleNamespace

    from PySide6.QtCore import QRect

    applied: list = []
    view = SimpleNamespace(
        _marquee_additive=False,
        _owner=None,
        _marquee_base=set(),
        apply_selection=lambda paths: applied.append(set(paths)),
    )
    monkeypatch.delenv("IMGSLI_GALLERY_NO_MARQUEE_COMMIT", raising=False)
    _marquee.on_rect_finish(view, QRect())
    assert applied == [set()]
