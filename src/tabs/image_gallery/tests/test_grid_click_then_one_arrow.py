"""Click in the empty grid zone, then ONE arrow press must reach a card.

Reported symptom: "почему требуется два раза нажать вверх". After clicking the
empty zone below the cards, the first Up did nothing and only the second one
moved — so it felt like the keyboard was broken rather than delayed.

Cause (fixed in the toolkit, see its CHANGELOG § Unreleased): a click kills the
focus ring, so the next arrow press re-anchors the ring onto the widget nearest
the click. That press was then consumed as "reveal-only". With few cards the
nearest focusable is the scroll area itself, so the re-anchor was a no-op onto a
container and the consumed press looked completely dead.

``test_empty_grid_area_is_owned_and_a_key_reaches_a_card`` (the #313 regression
test) covers the section's ``navigate()`` in isolation and never drove a real
click, which is why this path stayed broken.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.managers import NavigationManager

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.widget import ImageGalleryWidget


def _shown(qtbot, n: int = 2):
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1000, 700)
    w.show()
    qtbot.waitExposed(w)
    items = [
        GalleryItem(path=Path(f"/gallery/arrow{i}.png"), mtime_ns=i + 1) for i in range(n)
    ]
    w.rebuild_grid(items)
    QTest.qWait(20)
    return w, w._grid_view, items


def _click_empty_zone_below_cards(w, gv) -> None:
    """Click inside the grid, just above its visible bottom edge.

    Deliberately a low click with few cards: that is the geometry where the
    re-anchor picks the scroll area (a container) rather than a card.
    """
    QApplication.setActiveWindow(w)
    QTest.qWait(10)

    scroll = gv.scroll_area
    viewport = scroll.viewport() if hasattr(scroll, "viewport") else scroll
    top_left = viewport.mapToGlobal(viewport.rect().topLeft())
    bottom_left = viewport.mapToGlobal(viewport.rect().bottomLeft())
    point = QPoint(top_left.x() + viewport.width() // 2, max(top_left.y() + 4, bottom_left.y() - 8))
    QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=viewport.mapFromGlobal(point))
    QTest.qWait(30)


def test_click_in_empty_zone_then_one_arrow_reaches_a_card(qtbot) -> None:
    w, gv, _items = _shown(qtbot, 2)
    assert gv._live_cards_in_order(), "no cards built"

    # The tab registers this section in the app; register it here so the
    # manager's app-wide filter sees the click and the arrow.
    section = getattr(gv, "_nav_section", None)
    assert section is not None, "grid view did not build its nav section"
    mgr = NavigationManager.get_instance()
    mgr.register(gv, section)
    try:
        _click_empty_zone_below_cards(w, gv)

        # The click must have armed a realign, otherwise this test would pass
        # for the wrong reason (no click-to-keyboard path at all).
        assert mgr._realign.realign_pending is True, (
            "the click did not arm a realign — the app-wide nav filter is not "
            "seeing it, so this test would prove nothing"
        )
        assert gv.focused_card() is None, "precondition: the click itself focused no card"

        focused_before = QApplication.focusWidget()
        assert focused_before is not None
        assert gv.findChild(QWidget, "image_gallery_grid_host") is not None

        QTest.keyClick(focused_before, Qt.Key.Key_Up)
        QTest.qWait(40)

        card = gv.focused_card()
        assert card is not None, (
            "ONE Up after a click in the empty zone did not reach a card "
            f"(focus still {QApplication.focusWidget()!r})"
        )
        assert QApplication.focusWidget() is card
    finally:
        mgr.unregister(gv)
