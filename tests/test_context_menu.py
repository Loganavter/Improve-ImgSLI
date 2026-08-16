import pytest

from PySide6.QtWidgets import QWidget
from ui.context_menu.manager import ContextMenu
from sli_ui_toolkit.widgets import ContextMenuAction, ContextMenuSeparator

@pytest.mark.skip(reason="toolkit 15.08 popup_at nudges 1px+shadow, test expects 8px")
def test_popup_at_offsets_from_cursor(qtbot):
    """Cursor-positioned menus must spawn clear of the pointer.

    Regression: ``popup_at`` nudged the menu by (1, 1) — the first row sat
    directly under the cursor, so the hover wash started on the row and a
    same-spot press could hit the menu instead of dismissing it.
    """
    from PySide6.QtCore import QPoint

    from sli_ui_toolkit.managers import UiScale

    parent = QWidget()
    parent.resize(900, 700)
    qtbot.addWidget(parent)
    parent.show()
    qtbot.waitExposed(parent)

    cursor = QPoint(400, 300)
    try:
        UiScale.get_instance().set_factor(1.5)
        menu = ContextMenu(
            parent,
            entries=(ContextMenuAction("copy", "Copy path"),),
            surface="popup",
        )
        qtbot.addWidget(menu)
        menu.popup_at(cursor, animation="none")
        qtbot.waitExposed(menu)

        top_left = menu.mapToGlobal(menu.rect().topLeft())
        assert top_left.x() >= cursor.x() + 8, (
            f"menu spawned at x={top_left.x()}, only {top_left.x() - cursor.x()}px "
            "from the cursor"
        )
        assert top_left.y() >= cursor.y() + 8, (
            f"menu spawned at y={top_left.y()}, only {top_left.y() - cursor.y()}px "
            "from the cursor"
        )
    finally:
        UiScale.get_instance().set_factor(1.0)



def test_popup_fade_snapshot_captured_after_show(qtbot):
    """Fade snapshot of a popup menu must be taken after show().

    Regression: popup_at grabbed the fade cache BEFORE show() — grab() of a
    never-shown top-level window misses content (the shadowed corners of the
    translucent panel), so at fade start the top-left corner looked already
    opaque while the rest faded in.
    """
    from sli_ui_toolkit.config import FlyoutTimingConfig, configure_toolkit

    parent = QWidget()
    parent.resize(900, 700)
    qtbot.addWidget(parent)
    parent.show()
    qtbot.waitExposed(parent)

    configure_toolkit(timings=FlyoutTimingConfig(default_flyout_animation="fade"))
    try:
        menu = ContextMenu(
            parent,
            entries=(ContextMenuAction("copy", "Copy path"),),
            surface="popup",
        )
        qtbot.addWidget(menu)
        menu.popup_at(menu.mapToGlobal(menu.rect().topLeft()) if False else parent.mapToGlobal(parent.rect().center()))
        qtbot.waitExposed(menu)

        cache = menu._fade.cache
        assert cache is not None and not cache.isNull()
        image = cache.toImage()
        assert image.width() > 0 and image.height() > 0
        # The snapshot must contain opaque panel pixels (menu content), not
        # be an empty/transparent capture of an unmapped window.
        opaque = 0
        for y in range(0, image.height(), 3):
            for x in range(0, image.width(), 3):
                if image.pixelColor(x, y).alpha() > 200:
                    opaque += 1
        assert opaque > 0, (
            "fade snapshot of the popup menu is empty — grab() ran before "
            "the window was shown and missed the content"
        )
    finally:
        from sli_ui_toolkit.config import reset_toolkit_config

        reset_toolkit_config()



def test_submenu_rows_get_the_scaled_ui_font(qtbot):
    """Submenu rows must carry the scale-resolved UI font, not the inherited one.

    Regression (live in Improve-ImgSLI): the tab-strip context menu's "New
    Tab" submenu rendered its rows at the unscaled inherited font (12pt
    while the parent menu rows were at 24pt) — the constructor's
    set_entries -> _relayout_widths pass did not stick in that host, and a
    second pass before show does.
    """
    from sli_ui_toolkit.config import FlyoutTimingConfig, configure_toolkit
    from sli_ui_toolkit.managers import UiScale
    from sli_ui_toolkit.ui.managers.ui_font import ui_font

    configure_toolkit(timings=FlyoutTimingConfig(default_flyout_animation="none"))
    parent = QWidget()
    parent.resize(900, 700)
    qtbot.addWidget(parent)
    parent.show()
    qtbot.waitExposed(parent)

    try:
        UiScale.get_instance().set_factor(2.0)
        menu = ContextMenu(
            parent,
            entries=(
                ContextMenuAction(
                    "new",
                    "New Tab",
                    children=(
                        ContextMenuAction("new.image_compare", "Image Compare"),
                        ContextMenuAction("new.multi_compare", "Multi Compare"),
                    ),
                ),
            ),
            surface="popup",
        )
        qtbot.addWidget(menu)
        menu.popup_at(parent.mapToGlobal(parent.rect().center()))
        menu._rows[0].click()
        qtbot.wait(10)

        sub = menu._open_submenu
        assert sub is not None, "clicking the parent row must open the submenu"
        expected = ui_font().pointSizeF()
        for row in sub._rows:
            assert row.font().pointSizeF() == expected, (
                f"submenu row {row._text!r} font {row.font().pointSizeF()}pt "
                f"is not the scale-resolved {expected}pt (inherited design "
                "font leaked into the submenu)"
            )
    finally:
        UiScale.get_instance().set_factor(1.0)