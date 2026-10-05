"""Quick Look modal input grab: veil/X dismiss, flags survive repopulate.

A visible-but-hit-test-invisible veil passes every press to the gallery
beneath while looking modal (clicks select behind it, X/veil go dead).
Pinned here:
- X button fully dismisses (filters dropped, not just hidden);
- show_for re-asserts enabled + non-transparent AFTER populate/show;
- the overlay stays the topmost widget at veil points while visible.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.widget import ImageGalleryWidget


def _items(*names: str) -> list[GalleryItem]:
    return [
        GalleryItem(path=Path(f"/gallery/{n}"), mtime_ns=i + 1)
        for i, n in enumerate(names)
    ]


def _open(qtbot, n: int = 3):
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()
    qtbot.waitExposed(w)
    items = _items(*(f"i{i}.png" for i in range(n)))
    w.rebuild_grid(items)
    w.show_quick_look(items[0])
    return w, w._quick_look_overlay, items


def test_close_button_dismisses_overlay(qtbot) -> None:
    w, ov, _items = _open(qtbot)
    assert ov.isVisible()
    btn = ov._close_btn
    assert btn.isVisible() and btn.isEnabled()
    QTest.mouseClick(btn, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(btn.width() // 2, btn.height() // 2))
    assert not ov.isVisible()
    assert ov._filters_installed is False


def test_veil_click_dismisses_and_never_selects(qtbot) -> None:
    w, ov, _items = _open(qtbot)
    win = ov.window()
    pt = QPoint(40, 400)
    assert win.childAt(pt) is ov
    QTest.mouseClick(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pt)
    assert not ov.isVisible()


def test_show_for_restores_input_grab(qtbot) -> None:
    """A disturbed veil (transparent/disabled) heals on re-show."""
    w, ov, items = _open(qtbot)
    ov.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    ov.setEnabled(False)
    w.show_quick_look(items[1])
    assert ov.isEnabled()
    assert not ov.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert ov.window().childAt(QPoint(40, 400)) is ov
