"""Supervisor end-to-end probe for the reveal-only removal (toolkit fix).

The reported symptom: click the empty zone below the cards, then press Up —
it took two presses before anything moved, because the first press was
consumed as "reveal-only" and the realign target was the scroll area (a
container, not a card).

This drives the real path: the gallery registers its nav section (which
installs the app-wide filter), a real mouse click lands on the empty host,
then ONE arrow press must put focus on a card.

Temporary file: deleted right after the run.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.widget import ImageGalleryWidget


def _shown(qtbot, n: int = 8):
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1000, 700)
    w.show()
    qtbot.waitExposed(w)
    items = [GalleryItem(path=Path(f"/gallery/rev{i}.png"), mtime_ns=i + 1) for i in range(n)]
    w.rebuild_grid(items)
    QTest.qWait(20)
    return w, w._grid_view, items


def test_one_up_after_click_in_empty_zone_reaches_a_card(qtbot) -> None:
    w, gv, items = _shown(qtbot)
    assert gv._live_cards_in_order(), "no cards built"

    # The tab registers the grid's nav section (grid_view builds it, the tab
    # wires it into the manager, which installs the app-wide filter).
    from sli_ui_toolkit.managers import NavigationManager

    mgr = NavigationManager.get_instance()
    section = getattr(gv, "_nav_section", None)
    assert section is not None, "grid view did not build its nav section"
    mgr.register(gv, section)

    # Click well below the last card row — the empty host zone.
    from PySide6.QtWidgets import QWidget

    grid_host = None
    for cand in gv.findChildren(QWidget):
        if cand.objectName() == "image_gallery_grid_host":
            grid_host = cand
            break
    assert grid_host is not None, "grid host not found"

    # Clear focus first, so the click is the only thing that set it.
    QApplication.setActiveWindow(w)
    QTest.qWait(20)

    click_pos = grid_host.rect().center()
    click_pos.setY(max(1, grid_host.rect().height() - 20))
    QTest.mouseClick(grid_host, Qt.MouseButton.LeftButton, pos=click_pos)
    QTest.qWait(30)

    from sli_ui_toolkit.managers import NavigationManager

    mgr = NavigationManager.get_instance()
    print(
        "\n  DIAG filter_installed=", getattr(mgr, "_event_filter_installed", None),
        "sections=", [type(s).__name__ for _, s in getattr(mgr, "_sections", [])],
        "realign_pending=", mgr._realign.realign_pending,
        "last_click_pos=", mgr._realign.last_click_pos,
    )

    assert gv.focused_card() is None, (
        "precondition: a click in the empty zone should not itself focus a card"
    )

    focused_before = QApplication.focusWidget()
    QTest.keyClick(focused_before or w, Qt.Key.Key_Up)
    QTest.qWait(40)

    card = gv.focused_card()
    assert card is not None, (
        "ONE Up after a click in the empty zone did not reach a card "
        f"(focus still {QApplication.focusWidget()!r}) — reveal-only regression"
    )
    assert QApplication.focusWidget() is card
