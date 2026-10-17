"""Real-popup regression: the card menu must render at full size.

The existing card-menu tests all monkeypatch the opener, so a menu that
opens and then renders as a sliver (clipped child overlay) stayed green.
This test opens the REAL menu through ``popup_gallery_card_context_menu``
on a real grid card and measures the widget Qt actually shows.

Red-before: the manager's app-wide ``surface="in_window"`` policy parents
the menu to the source widget (the card Button). An in-window menu is a
plain child widget, so Qt clips it to the card's rectangle — the popup was
unusable (card-menu-size, 2026-10-17). Passing ``menu_parent=card.window()``
keeps the in-window surface but makes it a full overlay.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QWidget

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.ui.card.context_menu import popup_gallery_card_context_menu
from tabs.image_gallery.widget import ImageGalleryWidget


def _item(name: str) -> GalleryItem:
    return GalleryItem(path=Path("/g/" + name), mtime_ns=1, series_id="series_1", rank=1)


def test_card_menu_renders_unclipped(qtbot) -> None:
    from ui.context_menu.manager import get_context_menu_manager

    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(900, 600)
    w.show()
    items = [_item(f"{i}.png") for i in range(4)]
    w._grid_view.rebuild_grid(items)
    qtbot.wait(10)

    card = w._grid_view.card_for(items[0].path)
    assert card is not None

    popup_gallery_card_context_menu(
        card,
        w,
        items[0].path,
        global_pos=QPoint(300, 200),
        selection_count=0,
    )

    menu = get_context_menu_manager()._active_menu
    assert menu is not None, "card menu was not opened through the manager"
    try:
        # A real menu, not a stale/degenerate object.
        assert menu.isVisible()
        assert menu.isWindow() is False, (
            "in-window overlay expected; a Qt.Popup parented to the top-level "
            "is the Wayland compositing trap"
        )
        assert menu.width() >= 100, f"menu width {menu.width()} px"
        assert menu.height() >= 100, f"menu height {menu.height()} px"

        # Unclipped: Qt reports the whole menu as visible, not a card-sized
        # slice of it (the failure mode was a ~2 px artifact).
        visible = menu.visibleRegion().boundingRect()
        assert visible.width() == menu.width(), (
            f"menu clipped horizontally: {visible.width()} of {menu.width()} px"
        )
        assert visible.height() == menu.height(), (
            f"menu clipped vertically: {visible.height()} of {menu.height()} px"
        )

        rows = [child for child in menu.findChildren(QWidget) if hasattr(child, "action_id")]
        assert len(rows) >= 1, "menu opened with no action rows"
    finally:
        menu.hide()
