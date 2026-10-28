"""Hierarchical HelpDialog navigation and the host-composed document page."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent

from plugins.help.dialog import HelpDialog
from plugins.help.plugin import HelpPlugin
from plugins.help.tree import clear_help_tree_cache
from sli_ui_toolkit.widgets import SurfaceScrollArea, Text


@pytest.fixture(autouse=True)
def _help_tabs_discovered():
    from tabs.registry import TabRegistry

    TabRegistry().discover()
    TabRegistry().contribute_all_help()
    yield
    clear_help_tree_cache()


@pytest.fixture
def dark_theme(qapp):
    """Dark palette + registered palettes (Window #1e1e1e vs dialog.background #2b2b2b)."""
    from core.theme import DARK_THEME_PALETTE, LIGHT_THEME_PALETTE
    from sli_ui_toolkit.managers import ThemeManager

    tm = ThemeManager.get_instance()
    tm.register_palettes(LIGHT_THEME_PALETTE, DARK_THEME_PALETTE)
    tm.set_theme("dark", qapp, await_ripples=False)
    tm._flush_pending_theme()  # type: ignore[attr-defined]
    return tm


def test_help_dialog_opens_root_hub(qtbot):
    dialog = HelpDialog(current_language="en", app_name="Improve-ImgSLI")
    qtbot.addWidget(dialog)
    dialog.resize(880, 620)
    dialog.show()
    qtbot.waitExposed(dialog)
    assert isinstance(dialog._scroll, SurfaceScrollArea)
    assert dialog._nav.current_id == "root"
    assert not dialog._hub_page.isHidden()
    assert dialog._document.isHidden()
    # Geometry pass used to adjustSize() the scroll area → 0x0 blank pane.
    dialog._apply_dialog_geometry()
    assert dialog._scroll.width() > 200
    assert dialog._scroll.height() > 200
    assert dialog._hub_page.width() > 200
    assert dialog._hub_page._cards.count() >= 1


def test_help_dialog_content_surface_paints_dialog_background(qapp, qtbot, dark_theme):
    """Content scroll surface must be dialog.background, not the Window role.

    The hub page and document view are transparent custom widgets; before
    SurfaceScrollArea their substrate came from the stock QScrollArea
    viewport auto-fill (Window #1e1e1e dark). Sample the viewport below the
    workspace hub's cards (its trailing stretch pad).
    """
    dialog = HelpDialog(current_language="en", app_name="Improve-ImgSLI")
    qtbot.addWidget(dialog)
    # Tall viewport: the probe below must land on the trailing stretch pad,
    # whose size shrinks with every hub card added to the workspace hub —
    # at 620px six cards fill the viewport exactly and the sample hits a
    # card. ~1100px keeps hundreds of px of pad for any foreseeable hub
    # count (each card is ~90px).
    dialog.resize(880, 1100)
    dialog.show()
    qapp.processEvents()
    dialog._open_node("workspace")
    qapp.processEvents()
    # Scroll to the bottom so the sampled point lands on the trailing
    # stretch pad regardless of hub cardinality (each new hub card grows
    # the content; without this the sample hits a card). No-op when the
    # content is shorter than the viewport.
    bar = dialog._scroll.verticalScrollBar()
    bar.setValue(bar.maximum())
    qapp.processEvents()

    img = dialog._scroll.viewport().grab().toImage()
    assert img.width() > 0 and img.height() > 0
    pixel = img.pixelColor(img.width() // 2, img.height() - 20)
    assert pixel.name() == "#2b2b2b"
    assert pixel.name() != "#1e1e1e"


def test_help_dialog_content_surface_survives_polish(qapp, qtbot, dark_theme):
    """QStyle::polish at show() resets palettes — the token fill must persist."""
    dialog = HelpDialog(current_language="en", app_name="Improve-ImgSLI")
    qtbot.addWidget(dialog)
    # Tall viewport — same cardinality-proof sampling as the paints test:
    # the probe must land on trailing stretch, not on a hub card.
    dialog.resize(880, 1100)
    dialog.show()
    qapp.processEvents()
    dialog._open_node("workspace")
    qapp.processEvents()
    dialog._scroll.style().unpolish(dialog._scroll)
    dialog._scroll.style().polish(dialog._scroll)
    qapp.processEvents()
    # Same cardinality-proof sampling as above: bottom out the scroll so
    # the probe lands on the trailing stretch, not on a hub card.
    bar = dialog._scroll.verticalScrollBar()
    bar.setValue(bar.maximum())
    qapp.processEvents()

    img = dialog._scroll.viewport().grab().toImage()
    pixel = img.pixelColor(img.width() // 2, img.height() - 20)
    assert pixel.name() == "#2b2b2b"


def test_help_dialog_navigate_alias_magnifier(qtbot):
    dialog = HelpDialog(current_language="en", app_name="Improve-ImgSLI")
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.navigate_to("workspace.image_compare.magnifier", "freeze")
    assert dialog._nav.current_id == "workspace.image_compare.magnifier"
    assert not dialog._document.isHidden()
    assert dialog._document.scroll_to_anchor("freeze") is not None
    assert dialog._document.scroll_to_anchor("enabling") is not None


def test_help_document_page_is_text_with_host_owned_toc(qtbot, qapp):
    """The page body is the toolkit ``Text``; the TOC is host-owned chrome."""
    dialog = HelpDialog(current_language="en", app_name="Improve-ImgSLI")
    qtbot.addWidget(dialog)
    dialog.resize(900, 900)
    dialog.show()
    qtbot.waitExposed(dialog)
    dialog.navigate_to("workspace.image_compare.magnifier")
    qapp.processEvents()

    document = dialog._document
    assert isinstance(document, Text)
    assert document.mode() == "document"
    assert document.panel_fill is True
    assert document.plain_text().strip()
    # One TOC row per ``###`` section; the card is visible on a page with ≥2.
    assert dialog._toc.isVisible()
    assert len(dialog._toc._rows) == len(dialog._toc._items) >= 2
    assert all(row.isVisible() for row in dialog._toc._rows)
    # The TOC title follows the dialog language, not a widget-owned field.
    assert dialog._toc._title.text() == dialog._toc_title

    # Hub pages hide the whole composed page (padding + TOC + body).
    dialog._open_node("workspace")
    assert dialog._document.isHidden()
    assert dialog._document_page.isHidden()
    assert dialog._document.plain_text() == ""


def test_help_toc_click_scrolls_the_host_scroll_area(qtbot, qapp):
    """TOC → ``scroll_to_anchor`` y → the host scroll area (int contract)."""
    dialog = HelpDialog(current_language="en", app_name="Improve-ImgSLI")
    qtbot.addWidget(dialog)
    dialog.resize(900, 900)
    dialog.show()
    qtbot.waitExposed(dialog)
    dialog.navigate_to("workspace.image_compare.magnifier")
    qapp.processEvents()

    anchor = dialog._toc._items[-1][0]
    y = dialog._document.scroll_to_anchor(anchor)
    assert y is not None and y > 0
    target = dialog._document_scroll_target(y)
    bar = dialog._scroll.verticalScrollBar()
    bar.setValue(0)

    dialog._toc._rows[-1].click()
    qapp.processEvents()

    assert bar.value() == max(bar.minimum(), min(target, bar.maximum()))
    assert bar.value() > 0


def test_help_toc_click_owns_the_scroll_over_its_own_focus_reveal(qtbot, qapp):
    """The anchor scroll outranks the focus reveal the same click causes.

    A real click hands the clicked TOC row focus (Qt's press →
    ``setFocus(MouseFocusReason)``). A scroll area that follows focus then
    reveals that row — the toolkit's primitive for it is ``_ensure_visible``
    (``navigation_sections``), the exact call an ``AutoNavigationSection``
    makes after moving focus. That reveal is a *consequence* of the click, so
    it must not outrank the anchor the same click asked for: the host owns the
    resulting scroll position. Order matters and is asserted here — click
    (anchor applied) → reveal drags the bar back → the anchor re-assert lands
    after the handoff and wins.
    """
    from PySide6.QtWidgets import QApplication
    from sli_ui_toolkit.ui.managers.navigation_sections import _ensure_visible

    dialog = HelpDialog(current_language="en", app_name="Improve-ImgSLI")
    qtbot.addWidget(dialog)
    dialog.resize(900, 900)
    dialog.show()
    qtbot.waitExposed(dialog)
    dialog.navigate_to("workspace.image_compare.magnifier")
    qapp.processEvents()

    anchor = dialog._toc._items[-1][0]
    y = dialog._document.scroll_to_anchor(anchor)
    assert y is not None and y > 0
    bar = dialog._scroll.verticalScrollBar()
    expected = max(bar.minimum(), min(dialog._document_scroll_target(y), bar.maximum()))
    # The page must actually scroll, otherwise the reveal has nothing to fight.
    assert expected > 0
    bar.setValue(0)
    qapp.processEvents()

    row = dialog._toc._rows[-1]
    qtbot.mouseClick(row, Qt.MouseButton.LeftButton)
    # The handoff is real: the clicked row owns focus right after the press.
    assert QApplication.focusWidget() is row
    _ensure_visible(row)  # the reveal that handoff causes
    qapp.processEvents()  # the anchor re-assert lands after it

    assert bar.value() == expected


def test_help_figure_click_opens_the_host_lightbox(qtbot, qapp):
    """Image click surfaces the toolkit lightbox from the host, not ``Text``."""
    dialog = HelpDialog(current_language="en", app_name="Improve-ImgSLI")
    qtbot.addWidget(dialog)
    # Tall enough that the first figure is inside the scroll viewport: the
    # offscreen platform drops mouse events delivered below the visible area.
    dialog.resize(900, 900)
    dialog.show()
    qtbot.waitExposed(dialog)
    dialog.navigate_to("workspace.image_compare.magnifier")
    qapp.processEvents()

    engine = dialog._document._engine
    layout = engine._document_layout
    assert layout.pixmaps, "the magnifier page must carry a figure"
    center = layout.pixmaps[0].rect.center()
    local = QPointF(center.x() + 8, center.y() + 8)  # engine paints at PAD

    for kind in (
        QMouseEvent.Type.MouseButtonPress,
        QMouseEvent.Type.MouseButtonRelease,
    ):
        event = QMouseEvent(
            kind,
            local,
            local,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        qapp.notify(engine, event)
    qapp.processEvents()

    lightbox = dialog._lightbox
    assert lightbox is not None
    assert lightbox.isVisible()
    assert not lightbox._pixmap.isNull()
    lightbox.hide()


def test_help_dialog_navigate_unknown_page_renders_missing(qtbot):
    dialog = HelpDialog(current_language="en", app_name="Improve-ImgSLI")
    qtbot.addWidget(dialog)
    dialog.show()
    before = dialog._nav.current_id
    dialog.navigate_to("no_such_help_topic_xyz")
    assert dialog._nav.current_id == before
    assert not dialog._document.isHidden()
    assert "Missing page" in dialog._document.plain_text()


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
    # Hubs collapse the whole sidebar column — nav list *and* the search
    # header — so the root/main section owns the full width.
    assert not dialog._search_field.isVisible()
    assert dialog._splitter.sizes()[0] == 0
    dialog._open_node("workspace")
    assert dialog._search_field.isVisible()
    assert dialog._splitter.sizes()[0] >= HELP_SIDEBAR_DEFAULT_WIDTH - 40


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
    plugin.show_dialog(
        parent=None,
        language="ru",
        page="workspace.image_compare.magnifier",
        anchor="enabling",
    )
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


def test_help_hub_sync_icons_on_theme_change(qtbot):
    """Hub card icons are eager QIcons; theme switch must re-resolve them.

    ``resolve_help_icon`` now returns a monochrome tint of the source (never the
    resolver's own QIcon object) and caches by (name, colour); a theme change
    resolves a different colour and drops the stale tint. Here the colour is
    unchanged, so the invalidation the ThemeManager hook performs is applied
    explicitly to prove ``sync_icons`` rebuilds each eager card icon.
    """
    from PySide6.QtGui import QIcon, QPixmap

    from plugins.help.hub_page import HelpHubPage
    from plugins.help.icons import clear_help_icon_cache
    from plugins.help.tree import HelpNode

    light = QIcon()
    light.addPixmap(QPixmap(16, 16))
    dark = QIcon()
    dark.addPixmap(QPixmap(24, 24))
    icons = {"topic.svg": light}

    hub = HelpNode(
        node_id="hub",
        kind="hub",
        title="Hub",
        description="",
        children=("child",),
    )
    child = HelpNode(
        node_id="child",
        kind="page",
        title="Child",
        description="",
        icon="topic.svg",
    )
    page = HelpHubPage()
    qtbot.addWidget(page)
    page.set_icon_resolvers((lambda name: icons.get(name),))
    page.set_hub(hub, (child,))
    card = page._cards_by_id["child"]
    icon_region = next(r for r in card._regions if r.id == "icon")
    first_icon = icon_region.icon
    assert not first_icon.isNull()

    icons["topic.svg"] = dark
    clear_help_icon_cache()
    page.sync_icons()
    icon_region = next(r for r in card._regions if r.id == "icon")
    assert not icon_region.icon.isNull()
    assert icon_region.icon is not first_icon


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
