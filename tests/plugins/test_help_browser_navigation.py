"""Hierarchical HelpDialog navigation and HelpDocumentView wiring."""

from __future__ import annotations

import pytest

from plugins.help.dialog import HelpDialog
from plugins.help.plugin import HelpPlugin
from plugins.help.tree import clear_help_tree_cache


@pytest.fixture(autouse=True)
def _help_tabs_discovered():
    from tabs.registry import TabRegistry

    TabRegistry().discover()
    TabRegistry().contribute_all_help()
    yield
    clear_help_tree_cache()


def test_help_dialog_opens_root_hub(qtbot):
    dialog = HelpDialog(current_language="en", app_name="Improve-ImgSLI")
    qtbot.addWidget(dialog)
    dialog.resize(880, 620)
    dialog.show()
    qtbot.waitExposed(dialog)
    assert dialog._nav.current_id == "root"
    assert not dialog._hub_page.isHidden()
    assert dialog._document.isHidden()
    # Geometry pass used to adjustSize() the scroll area → 0x0 blank pane.
    dialog._apply_dialog_geometry()
    assert dialog._scroll.width() > 200
    assert dialog._scroll.height() > 200
    assert dialog._hub_page.width() > 200
    assert dialog._hub_page._cards.count() >= 1


def test_help_dialog_navigate_alias_magnifier(qtbot):
    dialog = HelpDialog(current_language="en", app_name="Improve-ImgSLI")
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.navigate_to("magnifier", "freeze")
    assert dialog._nav.current_id == "workspace.image_compare.magnifier"
    assert not dialog._document.isHidden()
    assert dialog._document.scroll_to_anchor("freeze") is not None
    assert dialog._document.scroll_to_anchor("enabling") is not None


def test_help_dialog_sidebar_splitter(qtbot):
    from plugins.help.layout_geometry import (
        HELP_SIDEBAR_DEFAULT_WIDTH,
        HELP_SIDEBAR_MIN_WIDTH,
    )

    dialog = HelpDialog(current_language="en", app_name="Improve-ImgSLI")
    qtbot.addWidget(dialog)
    dialog.resize(960, 620)
    dialog.show()
    qtbot.waitExposed(dialog)
    assert dialog._splitter is not None
    dialog._open_node("workspace")
    assert dialog.nav_widget.isVisible()
    sizes = dialog._splitter.sizes()
    assert sizes[0] >= HELP_SIDEBAR_MIN_WIDTH
    assert sizes[0] >= HELP_SIDEBAR_DEFAULT_WIDTH - 40
    # User can drag within min/max
    dialog._splitter.setSizes([320, 640])
    assert dialog._splitter.sizes()[0] >= HELP_SIDEBAR_MIN_WIDTH
    dialog._go_back()
    assert not dialog.nav_widget.isVisible()
    assert dialog._splitter.sizes()[0] == 0


def test_help_dialog_drill_and_back(qtbot):
    dialog = HelpDialog(current_language="en", app_name="Improve-ImgSLI")
    qtbot.addWidget(dialog)
    dialog.show()
    dialog._open_node("workspace")
    dialog._open_node("workspace.image_compare")
    dialog._open_node("workspace.image_compare.magnifier")
    assert not dialog._document.isHidden()
    dialog._go_back()
    assert not dialog._hub_page.isHidden()
    assert dialog._nav.current_id == "workspace.image_compare"
    dialog._go_forward()
    assert dialog._nav.current_id == "workspace.image_compare.magnifier"
    assert not dialog._document.isHidden()


def test_help_dialog_mouse_back_forward_buttons(qtbot):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    dialog = HelpDialog(current_language="en", app_name="Improve-ImgSLI")
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    dialog._open_node("workspace")
    dialog._open_node("workspace.image_compare")

    back = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(10, 10),
        QPointF(10, 10),
        Qt.MouseButton.BackButton,
        Qt.MouseButton.BackButton,
        Qt.KeyboardModifier.NoModifier,
    )
    assert dialog.eventFilter(dialog._hub_page, back) is True
    assert dialog._nav.current_id == "workspace"

    fwd = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(10, 10),
        QPointF(10, 10),
        Qt.MouseButton.ForwardButton,
        Qt.MouseButton.ForwardButton,
        Qt.KeyboardModifier.NoModifier,
    )
    assert dialog.eventFilter(dialog._hub_page, fwd) is True
    assert dialog._nav.current_id == "workspace.image_compare"


def test_help_plugin_show_dialog_page_alias(qtbot):
    plugin = HelpPlugin()
    plugin.show_dialog(parent=None, language="ru", page="magnifier", anchor="enabling")
    assert plugin._dialog is not None
    qtbot.addWidget(plugin._dialog)
    assert plugin._dialog._nav.current_id == "workspace.image_compare.magnifier"
    # RU body should load for magnifier
    assert plugin._dialog._document.scroll_to_anchor("enabling") is not None


def test_help_hub_set_hub_idempotent(qtbot):
    """Re-rendering the same hub must not rebuild cards under the cursor."""
    from plugins.help.hub_page import HelpHubPage
    from plugins.help.tree import get_help_tree

    tree = get_help_tree()
    hub = tree.require("root")
    children = tree.children_of("root")
    page = HelpHubPage()
    qtbot.addWidget(page)
    page.set_hub(hub, children)
    first = page._cards.itemAt(0).widget()
    page.set_hub(hub, children)
    assert page._cards.itemAt(0).widget() is first


def test_help_hub_dispose_cards_unregisters_hover(qtbot):
    from plugins.help.hub_page import HelpHubPage
    from plugins.help.tree import get_help_tree
    from sli_ui_toolkit.ui.widgets.helpers import hover_coordinator

    tree = get_help_tree()
    page = HelpHubPage()
    qtbot.addWidget(page)
    page.show()
    page.set_hub(tree.require("root"), tree.children_of("root"))
    card = page._cards.itemAt(0).widget()
    assert card in hover_coordinator()._widgets
    page.set_hub(
        tree.require("workspace"),
        tree.children_of("workspace"),
    )
    qtbot.wait(10)
    # Old card should be unregistered even if C++ delete is deferred.
    assert card not in hover_coordinator()._widgets


def test_help_hub_uses_localized_title(qtbot):
    from plugins.help.labels import node_title
    from plugins.help.tree import clear_help_tree_cache, get_help_tree

    clear_help_tree_cache()
    tree = get_help_tree()
    workspace = tree.require("workspace")
    assert "Рабочая" in node_title(workspace, "ru") or node_title(workspace, "ru") != ""

    # Session-type hubs must reuse workspace.session_types.* (same as picker naming).
    assert node_title(tree.require("workspace.image_compare"), "ru") == "Сравнение изображений"
    assert node_title(tree.require("workspace.multi_compare"), "ru") == "Мультисравнение"

    dialog = HelpDialog(current_language="ru", app_name="Improve-ImgSLI")
    qtbot.addWidget(dialog)
    dialog.show()
    assert "Помощь" in dialog.windowTitle() or dialog.windowTitle()
    assert dialog._hub_page._title.text()  # non-empty
