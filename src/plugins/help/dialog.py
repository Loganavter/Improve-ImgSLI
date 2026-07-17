"""Hierarchical help dialog: hubs, back bar, HelpDocumentView pages."""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QSize, QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from plugins.help.back_bar import HelpBackBar
from plugins.help.hub_page import HelpHubPage
from plugins.help.labels import node_title
from plugins.help.layout_geometry import (
    HELP_SIDEBAR_DEFAULT_WIDTH,
    HELP_SIDEBAR_MAX_WIDTH,
    HELP_SIDEBAR_MIN_WIDTH,
    apply_help_dialog_geometry,
)
from plugins.help.navigator import HelpNavigator
from plugins.help.tree import (
    get_help_tree,
    read_help_page_markdown,
    resolve_help_asset,
)
from resources.translations import tr
from shared_toolkit.ui.layout_sizing import (
    defer_dialog_geometry,
    handle_application_font_change,
    install_dialog_geometry_lifecycle,
)
from shared_toolkit.ui.overlay_layer import OverlayLayer
from shared_toolkit.ui.themed_dialog import ThemedDialog
from sli_ui_toolkit.ui.widgets.composite.help_sections import (
    normalize_help_language,
    toc_title_for_language,
)
from sli_ui_toolkit.widgets import (
    HelpDocumentView,
    MinimalistScrollBar,
    SidebarDialogShell,
)
from ui.icon_manager import AppIcon, get_app_icon

logger = logging.getLogger("ImproveImgSLI")


class HelpDialog(ThemedDialog):
    def __init__(self, current_language: str, app_name: str, parent=None):
        super().__init__(parent)
        self.current_language = current_language
        self.app_name = app_name
        self._tree = get_help_tree()
        self._nav = HelpNavigator(self._tree)
        self._pending_anchor: str | None = None
        self._syncing_sidebar = False
        self.overlay_layer = OverlayLayer(self)

        title = tr("help.help", language=current_language)
        self.setWindowTitle(title)
        self.setWindowIcon(get_app_icon(AppIcon.HELP))
        self.setObjectName("HelpDialog")
        # Independent top-level window (not transient-for the main shell), so
        # opening Help from Video Editor / Export does not bury those windows.
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setSizeGripEnabled(True)
        self.resize(880, 620)

        self._build_ui()
        self.install_dialog_geometry(self._apply_dialog_geometry)
        install_dialog_geometry_lifecycle(
            self,
            self._apply_dialog_geometry,
            theme_manager=self._theme_manager,
        )
        self.mark_theme_ui_ready()

        from shared_toolkit.ui.decorate_dialog import decorate_dialog

        decorate_dialog(self, title=title)
        self._render_current()
        self._mouse_nav_filter_installed = False

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._install_mouse_nav_filter()

    def hideEvent(self, event) -> None:
        self._remove_mouse_nav_filter()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self._remove_mouse_nav_filter()
        super().closeEvent(event)

    def _install_mouse_nav_filter(self) -> None:
        if self._mouse_nav_filter_installed:
            return
        app = QApplication.instance()
        if app is None:
            return
        app.installEventFilter(self)
        self._mouse_nav_filter_installed = True

    def _remove_mouse_nav_filter(self) -> None:
        if not self._mouse_nav_filter_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self._mouse_nav_filter_installed = False

    def eventFilter(self, watched, event) -> bool:
        if (
            event.type() == QEvent.Type.MouseButtonPress
            and self.isVisible()
            and isinstance(watched, QWidget)
            and (watched is self or self.isAncestorOf(watched))
            and isinstance(event, QMouseEvent)
        ):
            button = event.button()
            if button == Qt.MouseButton.BackButton and self._nav.can_go_back():
                self._go_back()
                return True
            if button == Qt.MouseButton.ForwardButton and self._nav.can_go_forward():
                self._go_forward()
                return True
        return super().eventFilter(watched, event)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._back_bar = HelpBackBar(self)
        self._back_bar.backRequested.connect(self._go_back)
        self._back_bar.segmentActivated.connect(self._on_crumb)
        root.addWidget(self._back_bar)

        self.shell = SidebarDialogShell(
            sidebar_width=HELP_SIDEBAR_DEFAULT_WIDTH,
            content_margins=(0, 0, 0, 0),
            content_spacing=0,
        )
        self.nav_widget = self.shell.sidebar
        self.nav_widget.enable_minimal_scrollbar()
        self.nav_widget.setMinimumWidth(HELP_SIDEBAR_MIN_WIDTH)
        self.nav_widget.setMaximumWidth(HELP_SIDEBAR_MAX_WIDTH)
        self.nav_widget.currentRowChanged.connect(self._on_sidebar_row)
        self._install_sidebar_splitter()

        # Help owns its content column; drop the unused pages stack so it cannot
        # leave a zero-size scroll sibling / compete for layout space.
        unused_stack = self.shell.pages_stack
        self.shell.content_layout.removeWidget(unused_stack)
        unused_stack.setParent(None)
        unused_stack.deleteLater()

        content_col = QWidget(self.shell.content_area)
        content_col.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        content_layout = QVBoxLayout(content_col)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self._scroll = QScrollArea(content_col)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBar(MinimalistScrollBar(parent=self._scroll))
        # QScrollArea can report sizeHint(0,0); without a floor, stretch=1 still
        # allocates zero height and the hub looks like a blank white pane.
        self._scroll.setMinimumSize(0, 1)
        self._scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        content_layout.addWidget(self._scroll, 1)

        self._content_host = QWidget()
        self._content_host.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._content_layout = QVBoxLayout(self._content_host)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        self._scroll.setWidget(self._content_host)

        self._hub_page = HelpHubPage(self._content_host)
        self._hub_page.childActivated.connect(self._open_node)
        self._document = HelpDocumentView(
            parent=self._content_host,
            resolve_asset=self._resolve_asset,
            open_external_links=True,
            show_toc=True,
            toc_title=toc_title_for_language(self.current_language),
        )
        self._document.linkActivated.connect(self._on_document_link)
        self._document.textContextMenuRequested.connect(self._on_text_context_menu)

        self._content_layout.addWidget(self._hub_page)
        self._content_layout.addWidget(self._document)
        self._hub_page.hide()
        self._document.hide()

        self.shell.content_layout.addWidget(content_col, 1)
        root.addWidget(self.shell, 1)

    def _install_sidebar_splitter(self) -> None:
        """Replace the shell HBox with a draggable sidebar | content splitter."""
        layout = self.shell.main_layout
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        self._splitter = QSplitter(Qt.Orientation.Horizontal, self.shell)
        self._splitter.setObjectName("HelpSidebarSplitter")
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(6)
        self._splitter.addWidget(self.shell.sidebar)
        self._splitter.addWidget(self.shell.content_area)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes(
            [HELP_SIDEBAR_DEFAULT_WIDTH, max(400, 880 - HELP_SIDEBAR_DEFAULT_WIDTH)]
        )
        layout.addWidget(self._splitter)

    def _set_sidebar_expanded(self, expanded: bool) -> None:
        splitter = getattr(self, "_splitter", None)
        if splitter is None:
            self.nav_widget.setVisible(expanded)
            return
        total = max(1, sum(splitter.sizes()) or self.width())
        if expanded:
            self.nav_widget.setMinimumWidth(HELP_SIDEBAR_MIN_WIDTH)
            self.nav_widget.setMaximumWidth(HELP_SIDEBAR_MAX_WIDTH)
            self.nav_widget.setVisible(True)
            left = splitter.sizes()[0] if splitter.sizes() else 0
            if left < HELP_SIDEBAR_MIN_WIDTH:
                left = HELP_SIDEBAR_DEFAULT_WIDTH
            splitter.setSizes([left, max(1, total - left)])
        else:
            self.nav_widget.setMinimumWidth(0)
            self.nav_widget.setMaximumWidth(0)
            self.nav_widget.setVisible(False)
            splitter.setSizes([0, total])

    def _apply_dialog_geometry(self) -> None:
        apply_help_dialog_geometry(self)

    def changeEvent(self, event: QEvent) -> None:
        handle_application_font_change(self, event)
        super().changeEvent(event)

    def update_language(self, new_language: str) -> None:
        self.current_language = new_language
        self.setWindowTitle(tr("help.help", language=self.current_language))
        self._document.set_toc_title(toc_title_for_language(self.current_language))
        self._render_current()
        defer_dialog_geometry(self, self._apply_dialog_geometry)

    def navigate_to(self, slug: str, anchor: str | None = None) -> None:
        """Open a topic by legacy slug, node id, or ``help://``-style page key."""
        try:
            node_id = self._tree.resolve_alias(slug)
        except KeyError:
            logger.warning("Help navigate_to: unknown page %r", slug)
            return
        self._pending_anchor = anchor
        self._nav.push(node_id)
        self._render_current()

    def _open_node(self, node_id: str) -> None:
        self._pending_anchor = None
        self._nav.push(node_id)
        self._render_current()

    def _go_back(self) -> None:
        self._pending_anchor = None
        self._nav.pop()
        self._render_current()

    def _go_forward(self) -> None:
        self._pending_anchor = None
        if not self._nav.can_go_forward():
            return
        self._nav.go_forward()
        self._render_current()

    def _on_crumb(self, node_id: str) -> None:
        self._pending_anchor = None
        self._nav.pop_to(node_id)
        self._render_current()

    def _on_sidebar_row(self, row: int) -> None:
        if self._syncing_sidebar or row < 0:
            return
        siblings = self._sidebar_sibling_ids()
        if row >= len(siblings):
            return
        target = siblings[row]
        if target == self._nav.current_id:
            return
        self._pending_anchor = None
        self._nav.replace_sibling(target)
        self._render_current()

    def _sidebar_sibling_ids(self) -> list[str]:
        current = self._nav.current_id
        if current == self._tree.root_id:
            return []
        return [n.node_id for n in self._tree.siblings_of(current)]

    def _render_current(self) -> None:
        node = self._nav.current_node()
        lang = self.current_language
        crumbs = tuple(
            (nid, node_title(self._tree.require(nid), lang))
            for nid in self._nav.stack
        )
        self._back_bar.set_breadcrumb(crumbs)
        self._back_bar.set_can_go_back(self._nav.can_go_back())
        self._sync_sidebar()

        open_topic = tr("help.open_topic", language=lang)
        if open_topic == "help.open_topic":
            open_topic = "Open topic"
        self._hub_page.set_language(lang, open_topic_label=open_topic)
        self._hub_page.set_icon_resolvers(self._tree.icon_resolvers)

        if node.kind == "hub":
            children = self._tree.children_of(node.node_id)
            self._hub_page.set_hub(node, children)
            self._hub_page.show()
            self._document.hide()
            self._document.clear()
        else:
            body = node.body or ""
            md = read_help_page_markdown(
                lang, body, body_root=node.body_root
            )
            self._document.set_markdown(md)
            self._document.show()
            self._hub_page.hide()
            if self._pending_anchor:
                anchor = self._pending_anchor
                self._pending_anchor = None
                QTimer.singleShot(0, lambda a=anchor: self._scroll_to_anchor(a))

        defer_dialog_geometry(self, self._apply_dialog_geometry)

    def _scroll_to_anchor(self, anchor: str) -> None:
        widget = self._document.scroll_to_anchor(anchor)
        if widget is not None:
            self._scroll.ensureWidgetVisible(widget, 0, 24)

    def _sync_sidebar(self) -> None:
        self._syncing_sidebar = True
        try:
            self.nav_widget.clear()
            siblings = self._sidebar_sibling_ids()
            current = self._nav.current_id
            current_row = -1
            lang = self.current_language
            for index, sid in enumerate(siblings):
                title = node_title(self._tree.require(sid), lang)
                item = self.nav_widget.add_item(title)
                item.setSizeHint(QSize(0, 35))
                if sid == current:
                    current_row = index
            if current_row >= 0:
                self.nav_widget.setCurrentRow(current_row)
            self._set_sidebar_expanded(bool(siblings))
        finally:
            self._syncing_sidebar = False

    def _resolve_asset(self, rel_path: str):
        return resolve_help_asset(rel_path, self._tree)

    def _on_text_context_menu(self, global_pos) -> None:
        from plugins.help.text_context_menu import open_help_text_context_menu

        open_help_text_context_menu(
            dialog=self,
            document=self._document,
            global_pos=global_pos,
            language=self.current_language,
        )

    def _on_document_link(self, href: str) -> None:
        if not href:
            return
        if href.startswith("#"):
            self._scroll_to_anchor(href[1:])
            return
        if href.startswith("help://"):
            rest = href[len("help://") :]
            page, _, anchor = rest.partition("#")
            self.navigate_to(page, anchor or None)
            return
        if href.startswith(("http://", "https://")):
            QDesktopServices.openUrl(QUrl(href))
