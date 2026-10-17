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


def test_card_menu_with_a_page_translator_stays_full_size(qtbot) -> None:
    """A localized card menu is a real menu, not a sliver.

    Regression for ``card-menu-collapse`` (2026-10-17): the card path used to
    bind a translator to the menu AFTER ``popup_at``. During the show-time fade
    the flyout's container is hidden, so ``retranslate`` -> ``_relayout_widths``
    -> ``adjustSize`` measured an empty layout and collapsed the menu (16x16 in
    the live app, 94x272 here). Labels are now localized when the entries are
    built, exactly like every other context menu, and the shown menu is never
    re-laid-out.
    """
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

    def tr(key: str, default: str | None = None) -> str:
        return default if default is not None else key

    popup_gallery_card_context_menu(
        card,
        w,
        items[0].path,
        global_pos=QPoint(300, 200),
        selection_count=0,
        translate=tr,
    )
    menu = get_context_menu_manager()._active_menu
    assert menu is not None, "card menu was not opened"
    try:
        qtbot.wait(60)  # let a show-time fade settle if the toolkit runs one
        assert (menu.width(), menu.height()) != (16, 16), (
            f"translated card menu collapsed to {menu.width()}x{menu.height()}"
        )
        assert menu.width() >= 100 and menu.height() >= 100, (
            f"translated card menu is a sliver: {menu.width()}x{menu.height()}"
        )
        rows = [c for c in menu.findChildren(QWidget) if hasattr(c, "action_id")]
        assert len(rows) >= 1, "menu opened with no action rows"
    finally:
        menu.hide()
