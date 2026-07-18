"""Help body text context menu uses app ContextMenuManager."""

from __future__ import annotations

import sys

import pytest

from plugins.help.dialog import HelpDialog
from plugins.help.text_context_menu import open_help_text_context_menu
from plugins.help.tree import clear_help_tree_cache
from ui.context_menu.manager import get_context_menu_manager, rmb_context_menu_surface


@pytest.fixture(autouse=True)
def _help_tabs_discovered():
    from tabs.registry import TabRegistry

    TabRegistry().discover()
    TabRegistry().contribute_all_help()
    yield
    clear_help_tree_cache()


def test_help_text_context_menu_uses_platform_surface(qtbot):
    dialog = HelpDialog(current_language="en", app_name="Improve-ImgSLI")
    qtbot.addWidget(dialog)
    dialog.resize(880, 620)
    dialog.show()
    qtbot.waitExposed(dialog)

    dialog.navigate_to("introduction")
    global_pos = dialog._document.mapToGlobal(dialog._document.rect().center())
    open_help_text_context_menu(
        dialog=dialog,
        document=dialog._document,
        global_pos=global_pos,
        language="en",
    )
    qtbot.wait(10)

    menu = get_context_menu_manager()._active_menu
    assert menu is not None
    assert menu.isVisible()
    assert [row._text for row in menu._rows] == [
        "Copy",
        "Copy as Markdown",
        "Select all",
    ]
    assert not menu._rows[0].isEnabled()
    assert not menu._rows[1].isEnabled()
    assert menu._surface == rmb_context_menu_surface()
    # Windows stays in-window to avoid CSD alpha corruption; elsewhere popup.
    assert menu.isWindow() is (rmb_context_menu_surface() == "popup")
    assert menu._logical_parent is dialog
    menu.hide()


def test_help_text_context_menu_enables_copy_with_selection(qtbot):
    dialog = HelpDialog(current_language="en", app_name="Improve-ImgSLI")
    qtbot.addWidget(dialog)
    dialog.resize(880, 620)
    dialog.show()
    qtbot.waitExposed(dialog)

    dialog.navigate_to("introduction")
    dialog._document.select_all_text()
    global_pos = dialog._document.mapToGlobal(dialog._document.rect().center())
    open_help_text_context_menu(
        dialog=dialog,
        document=dialog._document,
        global_pos=global_pos,
        language="en",
    )
    qtbot.wait(10)

    menu = get_context_menu_manager()._active_menu
    assert menu is not None
    assert menu._rows[0].isEnabled()
    assert menu._rows[1].isEnabled()
    menu.hide()


def test_help_select_all_includes_headings_and_paragraphs(qtbot):
    dialog = HelpDialog(current_language="en", app_name="Improve-ImgSLI")
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.navigate_to("introduction")

    dialog._document.select_all_text()
    selected = dialog._document.selected_plain_text()
    assert selected
    assert selected == dialog._document.plain_text()


def test_rmb_context_menu_surface_windows_avoids_popup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    assert rmb_context_menu_surface() == "in_window"
    monkeypatch.setattr(sys, "platform", "linux")
    assert rmb_context_menu_surface() == "popup"
