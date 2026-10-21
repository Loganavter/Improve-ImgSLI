"""Help body text context menu uses app ContextMenuManager."""

from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QApplication

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


def test_help_text_context_menu_stays_an_in_window_child(qtbot):
    """The text-selection menu is an in-window child of the dialog.

    Falsification: opting this menu out to a native ``Qt.Popup`` top-level
    ("a real popup") breaks it on Wayland/Mutter - the popup's wl_surface
    gets NO compositor role (no xdg_surface, no subsurface), so the
    compositor never composites it: the menu is painted but nothing appears,
    and the host window's drawing is disturbed (live report 2026-10-21; the
    protocol proof lives in internal-docs). An in-window child is drawn into
    the dialog's own surface and is always visible.
    """
    dialog = HelpDialog(current_language="en", app_name="Improve ImgSLI")
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
    # the app-wide RMB policy, not a per-call popup opt-out
    assert menu._surface == "in_window"
    assert not menu.isWindow()
    # a child of the dialog: drawn into the dialog's own surface
    assert menu._logical_parent is dialog
    menu.hide()


def test_help_text_context_menu_stays_in_window_under_the_app_popup_default(qtbot):
    """The manager policy must win over the toolkit's app-wide ``popup``.

    Live report 2026-10-22 (Wayland): after opening this menu once, the help
    dialog's frame broke (an extra bottom-right badge) and resizing lagged —
    the documented "Qt.Popup parented to the top-level breaks the host's
    compositing" failure (inv-2026-10-06-ql-rhi-menu-first). Cause: the app
    bootstrap configures the toolkit global to ``popup``
    (``ui/icon_manager.py``) and the manager forgot to pass its own
    ``in_window`` policy to ``ContextMenu``. Before the fix this menu IS the
    popup window (``isWindow() is True``).
    """
    from sli_ui_toolkit import config as tk_config

    tk_config.configure_toolkit(context_menu_surface="popup")
    assert tk_config.get_context_menu_surface() == "popup"

    dialog = HelpDialog(current_language="en", app_name="Improve-ImgSLI")
    qtbot.addWidget(dialog)
    dialog.resize(880, 620)
    dialog.show()
    qtbot.waitExposed(dialog)

    dialog.navigate_to("platform.getting_started")
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
    assert menu._surface == "in_window"
    assert not menu.isWindow()
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


def test_help_copy_markdown_uses_the_host_page_source(qtbot):
    """Copy-as-Markdown maps the selection against the page markdown the host
    rendered (``Text.set_blocks`` clears the widget's own source)."""
    from PySide6.QtGui import QGuiApplication

    dialog = HelpDialog(current_language="en", app_name="Improve-ImgSLI")
    qtbot.addWidget(dialog)
    dialog.resize(880, 620)
    dialog.show()
    qtbot.waitExposed(dialog)

    dialog.navigate_to("introduction")
    dialog._document.select_all_text()
    source = dialog._document_source_markdown
    assert source.strip()

    global_pos = dialog._document.mapToGlobal(dialog._document.rect().center())
    open_help_text_context_menu(
        dialog=dialog,
        document=dialog._document,
        global_pos=global_pos,
        language="en",
        source_markdown=source,
    )
    qtbot.wait(10)
    menu = get_context_menu_manager()._active_menu
    assert menu is not None
    menu._finish_row_click("help.text.copy_markdown", None)
    qtbot.wait(10)

    assert QGuiApplication.clipboard().text() == source
    # Copy is a toolkit-standard action: it ends the selection gesture.
    assert dialog._document.hasSelectedText() is False
    # A popup-surface menu deletes itself on hide (it is ephemeral), so the
    # wrapper may already be gone — that is the documented popup contract.
    try:
        menu.hide()
    except RuntimeError:
        pass


def test_help_text_context_menu_keeps_the_selection(qtbot):
    """The right-click that OPENS the menu must not clear the selection.

    Falsification: the document canvas used to reset the selection on ANY
    mouse press, so the menu was built from an empty selection and every
    copy row came up disabled (2026-10-21). The canvas now ignores
    non-left buttons (toolkit: text/engine/events.py), so a real
    right-click keeps the selection and the copy rows stay enabled.
    """
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    dialog = HelpDialog(current_language="en", app_name="Improve-ImgSLI")
    qtbot.addWidget(dialog)
    dialog.resize(880, 620)
    dialog.show()
    qtbot.waitExposed(dialog)

    dialog.navigate_to("introduction")
    document = dialog._document
    document.select_all_text()
    qtbot.wait(10)
    selected = document.selected_plain_text()
    assert selected

    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(60.0, 40.0),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(document.canvas(), press)
    qtbot.wait(10)
    assert document.selected_plain_text() == selected

    global_pos = document.mapToGlobal(QPoint(60, 40))
    open_help_text_context_menu(
        dialog=dialog,
        document=document,
        global_pos=global_pos,
        language="en",
    )
    qtbot.wait(10)

    menu = get_context_menu_manager()._active_menu
    assert menu is not None
    assert menu._rows[0].isEnabled()
    assert menu._rows[1].isEnabled()
    try:
        menu.hide()
    except RuntimeError:
        pass


def test_rmb_surface_is_in_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # RMB menus are in-window overlay children by design (see
    # ``ui.context_menu.manager.rmb_context_menu_surface``): a native Qt.Popup
    # tears down its xdg_popup surface on close, and a widget shown right after
    # (e.g. the Ask AI flyout) then flashes the global busy cursor. The value is
    # platform/version independent.
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("sli_ui_toolkit.__version__", "3.1.3")
    assert rmb_context_menu_surface() == "in_window"


def test_help_copy_markdown_copies_only_the_selected_list_items(qtbot):
    """Owner report 2026-10-21: selecting two labels copied the WHOLE page.

    The plain selection never occurs verbatim in the source (the index strips
    ``1.``/``**`` and joins blocks with blank lines), and the old fallback
    returned the full page markdown. The copy now maps through the parsed
    blocks' source geometry, so the clipboard holds exactly those two lines.
    """
    from PySide6.QtGui import QGuiApplication

    dialog = HelpDialog(current_language="en", app_name="Improve-ImgSLI")
    qtbot.addWidget(dialog)
    dialog.resize(880, 620)
    dialog.show()
    qtbot.waitExposed(dialog)

    dialog.navigate_to("platform.getting_started")
    document = dialog._document
    index = document.canvas()._document_index
    plain = index.text
    items = [
        segment
        for segment in index.segments
        if plain[segment.start : segment.end].startswith(("3. ", "4. "))
    ]
    assert len(items) == 2

    def _select_items() -> None:
        document.canvas()._doc_selection.set_range(items[0].start, items[1].end)

    def _open_menu():
        global_pos = document.mapToGlobal(document.rect().center())
        open_help_text_context_menu(
            dialog=dialog,
            document=document,
            global_pos=global_pos,
            language="en",
            source_markdown=source,
        )
        qtbot.wait(10)
        menu = get_context_menu_manager()._active_menu
        assert menu is not None
        return menu

    source = dialog._document_source_markdown
    first = source.index("3. Load one image")
    second = source.index("4. Drag the **Divider**")
    expected = source[first : source.index("\n", second)]
    assert expected.strip() != source.strip()

    # Plain Copy: the plain selection, and the highlight is dropped.
    _select_items()
    menu = _open_menu()
    menu._finish_row_click("help.text.copy", None)
    qtbot.wait(10)
    assert QGuiApplication.clipboard().text() == plain[items[0].start : items[1].end]
    assert document.hasSelectedText() is False
    try:
        menu.hide()
    except RuntimeError:
        pass

    # Copy as Markdown: exactly the two source lines, highlight dropped too.
    _select_items()
    menu = _open_menu()
    menu._finish_row_click("help.text.copy_markdown", None)
    qtbot.wait(10)
    assert QGuiApplication.clipboard().text() == expected
    assert document.hasSelectedText() is False
    try:
        menu.hide()
    except RuntimeError:
        pass
