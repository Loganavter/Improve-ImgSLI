"""Hierarchical help dialog: hubs, back bar, HelpDocumentView pages."""
# Audit-Meta: pattern=qdialog-wiring reason="one Help QDialog — HelpDocumentView + search wiring"

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QObject, QSize, QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from plugins.help import topic_search
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
    HelpNode,
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
from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.ui.widgets.composite.help_sections import (
    normalize_help_language,
    toc_title_for_language,
)
from sli_ui_toolkit.widgets import (
    CustomLineEdit,
    HelpDocumentView,
    MinimalistScrollBar,
    SidebarDialogShell,
)
from ui.icon_manager import AppIcon, get_app_icon
from ui.layout_spacing import sidebar_header_host

logger = logging.getLogger("ImproveImgSLI")


class _HelpMouseNavFilter(QObject):
    """App-wide mouse back/forward filter owned by ``HelpDialog``.

    Must not be the dialog itself: if ``HelpDialog`` is the installed filter,
    ``deleteLater`` leaves a dangling app filter and theme/paint storms then
    blow up with ``HelpDialog already deleted`` inside ``eventFilter``.
    A child ``QObject`` is destroyed with the dialog and Qt removes it from the
    application filter list automatically.
    """

    def __init__(self, dialog: HelpDialog) -> None:
        super().__init__(dialog)
        self._dialog = dialog

    def eventFilter(self, watched, event) -> bool:
        dialog = self._dialog
        try:
            from shiboken6 import isValid

            if not isValid(dialog) or not isValid(self):
                return False
        except ImportError:
            pass
        if (
            event.type() == QEvent.Type.MouseButtonPress
            and dialog.isVisible()
            and isinstance(watched, QWidget)
            and (watched is dialog or dialog.isAncestorOf(watched))
            and isinstance(event, QMouseEvent)
        ):
            button = event.button()
            if button == Qt.MouseButton.BackButton and dialog._nav.can_go_back():
                dialog._go_back()
                return True
            if button == Qt.MouseButton.ForwardButton and dialog._nav.can_go_forward():
                dialog._go_forward()
                return True
        return False


class HelpDialog(ThemedDialog):
    def __init__(self, current_language: str, app_name: str, parent=None):
        super().__init__(parent)
        self.current_language = current_language
        self.app_name = app_name
        self._tree = get_help_tree()
        self._nav = HelpNavigator(self._tree)
        self._pending_anchor: str | None = None
        self._syncing_sidebar = False
        self._search_mode = False
        self.overlay_layer = OverlayLayer(self)
        self._mouse_nav_filter: _HelpMouseNavFilter | None = None

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
        self.resize(scaled_px(880), scaled_px(620))

        self._build_ui()
        self.install_dialog_geometry(self._apply_dialog_geometry)
        # ThemedDialog already reconnects geometry on theme_changed; do not pass
        # theme_manager here — a bare lambda would outlive deleteLater'd dialogs.
        install_dialog_geometry_lifecycle(self, self._apply_dialog_geometry)
        self.mark_theme_ui_ready()

        from shared_toolkit.ui.decorate_dialog import decorate_dialog

        decorate_dialog(self, title=title)
        self._setup_topic_search()
        self._setup_help_navigation()
        self._render_current()

    def _setup_help_navigation(self) -> None:
        """Wire keyboard navigation for Help: back bar → sidebar (search+list) ↔ content."""
        try:
            from sli_ui_toolkit.managers import NavigationManager
            from sli_ui_toolkit.ui.managers.navigation_sections import (
                AutoNavigationSection,
                ToolbarRowsSection,
            )

            if getattr(self, "_help_navigation_installed", None):
                return
            self._help_navigation_installed = True

            # Back bar (top) — single row with back + crumbs
            back_section = ToolbarRowsSection(
                lambda: [self._back_bar] if self._back_bar.isVisible() else [],
                tag="help-backbar",
            )

            # Sidebar column (search field + nav list) — auto-discovers both.
            sidebar_column = getattr(self.shell, "sidebar_column", None)
            sidebar_owner = sidebar_column if sidebar_column is not None else self.nav_widget
            sidebar_section = AutoNavigationSection(
                sidebar_owner, tag="help-sidebar"
            )

            def _focus_content() -> bool:
                host = getattr(self, "_content_host", None)
                if host is None:
                    return False
                return NavigationManager.get_instance().focus_section_for_owner(host)

            def _focus_sidebar() -> bool:
                return NavigationManager.get_instance().focus_section_for_owner(
                    sidebar_owner
                )

            sidebar_section._on_exit_right = lambda reason=None: _focus_content()  # type: ignore[attr-defined]
            content_host = getattr(self, "_content_host", None)
            content_section = None
            if content_host is not None:
                content_section = AutoNavigationSection(
                    content_host, tag="help-content"
                )
                content_section._on_exit_left = lambda reason=None: _focus_sidebar()  # type: ignore[attr-defined]

            mgr = NavigationManager.get_instance()
            mgr.register(self._back_bar, back_section)
            mgr.register(sidebar_owner, sidebar_section)
            if content_host is not None and content_section is not None:
                mgr.register(content_host, content_section)

            self._help_back_section = back_section
            self._help_sidebar_section = sidebar_section
            self._help_content_section = content_section
        except Exception:
            logger.exception("help navigation setup failed")

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._install_mouse_nav_filter()
        QTimer.singleShot(0, self._focus_help_container)
        QTimer.singleShot(60, self._focus_help_container)

    def _focus_help_container(self) -> None:
        try:
            from shiboken6 import isValid

            if not isValid(self) or not self.isVisible():
                return
            try:
                from sli_ui_toolkit.managers import NavigationManager

                NavigationManager.get_instance()._last_input_keyboard = True
            except Exception:
                pass
            reason = Qt.FocusReason.OtherFocusReason
            # Prefer the sidebar column (search+list) when visible — like main
            # window, keep focus on the container before first arrow, not on an
            # invisible Button. Down from the container will land on the first
            # visible row (search field) with a visible ring.
            sidebar_column = getattr(self.shell, "sidebar_column", None)
            if sidebar_column is not None and sidebar_column.isVisible():
                sidebar_column.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                sidebar_column.setFocus(reason)
                return
            if self.nav_widget.isVisible() and self.nav_widget.count() > 0:
                self.nav_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                self.nav_widget.setFocus(reason)
                return
            if self._back_bar.isVisible():
                self._back_bar.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                self._back_bar.setFocus(reason)
                return
            host = getattr(self, "_content_host", None)
            if host is not None and isValid(host):
                host.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                host.setFocus(reason)
        except Exception:
            pass

    def hideEvent(self, event) -> None:
        self._remove_mouse_nav_filter()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self._remove_mouse_nav_filter()
        super().closeEvent(event)

    def deleteLater(self) -> None:
        self._remove_mouse_nav_filter()
        super().deleteLater()

    def _install_mouse_nav_filter(self) -> None:
        if self._mouse_nav_filter is not None:
            return
        app = QApplication.instance()
        if app is None:
            return
        filt = _HelpMouseNavFilter(self)
        app.installEventFilter(filt)
        self._mouse_nav_filter = filt

    def _remove_mouse_nav_filter(self) -> None:
        filt = self._mouse_nav_filter
        if filt is None:
            return
        app = QApplication.instance()
        if app is not None:
            try:
                app.removeEventFilter(filt)
            except RuntimeError:
                pass
        self._mouse_nav_filter = None
        try:
            filt.deleteLater()
        except RuntimeError:
            pass

    def eventFilter(self, watched, event) -> bool:
        # Tests call this directly for mouse back/forward; delegate to the
        # dedicated filter object when present.
        filt = self._mouse_nav_filter
        if filt is not None:
            return filt.eventFilter(watched, event)
        return False

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._back_bar = HelpBackBar(self)
        self._back_bar.backRequested.connect(self._go_back)
        self._back_bar.segmentActivated.connect(self._on_crumb)
        root.addWidget(self._back_bar)

        self._search_field = CustomLineEdit()
        self._search_field.setObjectName("HelpSearchField")
        self._search_field.setPlaceholderText(
            tr("help.search_placeholder", language=self.current_language)
        )
        self._search_field.setClearButtonEnabled(True)
        # The sidebar can shrink to HELP_SIDEBAR_MIN_WIDTH — keep the field's
        # own minimum well below that so it never blocks the drag.
        self._search_field.setMinimumWidth(scaled_px(1))

        self.shell = SidebarDialogShell(
            sidebar_width=HELP_SIDEBAR_DEFAULT_WIDTH,
            content_margins=(0, 0, 0, 0),
            content_spacing=0,
            sidebar_header=sidebar_header_host(self._search_field),
        )
        self.nav_widget = self.shell.sidebar
        self.nav_widget.enable_minimal_scrollbar()
        self.nav_widget.setMinimumWidth(scaled_px(HELP_SIDEBAR_MIN_WIDTH))
        self.nav_widget.setMaximumWidth(scaled_px(HELP_SIDEBAR_MAX_WIDTH))
        if self.shell.sidebar_column is not None:
            # The shell pins the whole column to sidebar_width (280); lower
            # it to the same minimum as the nav list so the splitter can
            # actually shrink the sidebar (the field's own minimum is ~0).
            self.shell.sidebar_column.setMinimumWidth(
                scaled_px(HELP_SIDEBAR_MIN_WIDTH)
            )
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
        self._scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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
            open_external_links=False,
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

        # With a sidebar header (search field) the splitter owns the whole
        # sidebar column, not the bare nav list.
        sidebar_widget = (
            self.shell.sidebar_column
            if self.shell.sidebar_column is not None
            else self.shell.sidebar
        )
        self._splitter = QSplitter(Qt.Orientation.Horizontal, self.shell)
        self._splitter.setObjectName("HelpSidebarSplitter")
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(scaled_px(6))
        self._splitter.addWidget(sidebar_widget)
        self._splitter.addWidget(self.shell.content_area)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes(
            [
                scaled_px(HELP_SIDEBAR_DEFAULT_WIDTH),
                max(
                    scaled_px(400),
                    scaled_px(880) - scaled_px(HELP_SIDEBAR_DEFAULT_WIDTH),
                ),
            ]
        )
        layout.addWidget(self._splitter)

    def _set_sidebar_expanded(self, expanded: bool) -> None:
        splitter = getattr(self, "_splitter", None)
        if splitter is None:
            self.nav_widget.setVisible(expanded)
            return
        total = max(1, sum(splitter.sizes()) or self.width())
        if expanded:
            self.nav_widget.setMinimumWidth(scaled_px(HELP_SIDEBAR_MIN_WIDTH))
            self.nav_widget.setMaximumWidth(scaled_px(HELP_SIDEBAR_MAX_WIDTH))
            self.nav_widget.setVisible(True)
            if self.shell.sidebar_column is not None:
                self.shell.sidebar_column.setVisible(True)
            left = splitter.sizes()[0] if splitter.sizes() else 0
            if left < scaled_px(HELP_SIDEBAR_MIN_WIDTH):
                left = scaled_px(HELP_SIDEBAR_DEFAULT_WIDTH)
            splitter.setSizes([left, max(1, total - left)])
        else:
            # Collapse the whole sidebar column — nav list *and* the search
            # header: at hubs (no siblings) the root/main section owns the
            # full width, so the search field is not shown there.
            self.nav_widget.setVisible(False)
            if self.shell.sidebar_column is not None:
                self.shell.sidebar_column.setVisible(False)
            splitter.setSizes([0, total])

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if getattr(self, "_search_mode", False):
                self.clear_topic_search()
            event.accept()
            return
        super().keyPressEvent(event)

    def _apply_dialog_geometry(self) -> None:
        apply_help_dialog_geometry(self)

    def changeEvent(self, event: QEvent) -> None:
        handle_application_font_change(self, event)
        super().changeEvent(event)

    def on_dialog_theme_changed(self) -> None:
        # Hub cards store eager QIcons; same freeze as session_picker had.
        self.setWindowIcon(get_app_icon(AppIcon.HELP))
        self._hub_page.sync_icons()

    def update_language(self, new_language: str) -> None:
        self.current_language = new_language
        self.setWindowTitle(tr("help.help", language=self.current_language))
        self._document.set_toc_title(toc_title_for_language(self.current_language))
        self._search_field.setPlaceholderText(
            tr("help.search_placeholder", language=self.current_language)
        )
        if self._search_mode:
            # Re-run the live search so result rows match the new language.
            self._apply_topic_search()
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
        if self._search_mode:
            self._on_search_result_activated(row)
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

    # ---- topic search (matches titles + page content, ranked) ----
    # Logic lives in plugins/help/topic_search.py — see docs/dev/CODE_PATTERNS.md.

    def _setup_topic_search(self) -> None:
        topic_search._setup_topic_search(self)

    def _on_search_text_changed(self, _text: str) -> None:
        topic_search._on_search_text_changed(self, _text)

    def _apply_topic_search(self) -> None:
        topic_search._apply_topic_search(self)

    def _rank_topic_matches(self, query: str) -> list[tuple[str, int, bool]]:
        return topic_search._rank_topic_matches(self, query)

    def _on_search_result_activated(self, row: int) -> None:
        topic_search._on_search_result_activated(self, row)

    def clear_topic_search(self) -> None:
        topic_search.clear_topic_search(self)

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
        QTimer.singleShot(0, self._restore_focus_after_window_change)

    def _restore_focus_after_window_change(self) -> None:
        try:
            from shiboken6 import isValid
            from PySide6.QtWidgets import QApplication
            if not isValid(self) or not self.isVisible():
                return
            focused = QApplication.focusWidget()
            # If focused is still inside help dialog and visible, keep it
            # (e.g. back button still there after navigation). Only restore
            # when focus was lost (deleted widget, window, or title bar).
            if focused is not None and isValid(focused) and self.isAncestorOf(focused) and focused.isVisible():
                # Keep focus if it is a navigable Button/LineEdit/Canvas
                # but if it is the CustomTitleBar or OverlayScrollArea (as seen
                # in log after Enter on back button: focused went to
                # OverlayScrollArea -> HelpDocumentBodyCanvas -> CustomTitleBar),
                # we should move it to the new content.
                if isinstance(focused, type(self._back_bar)) and focused is self._back_bar:
                    pass  # container itself, not a button
                elif focused.objectName() in ("HelpBackBar", "HelpSearchField", "HelpDialog"):
                    pass
                else:
                    # Check if focused is still a valid navigable widget
                    # If it is inside help dialog and not the title bar, keep it
                    if not isinstance(focused, type(self.windowHandle())):
                        # Simple check: if focused is inside _content_host or nav_widget or _back_bar and visible, keep
                        if (self._content_host.isAncestorOf(focused) or self.nav_widget.isAncestorOf(focused) or self._back_bar.isAncestorOf(focused) or focused is self._search_field):
                            return
            # Focus was lost or on title bar/overlay — move to new content or sidebar
            # Prefer content first card when hub, otherwise sidebar
            try:
                from sli_ui_toolkit.managers import NavigationManager
                NavigationManager.get_instance()._last_input_keyboard = True
            except Exception:
                pass
            # Try content first (hub cards or document canvas)
            host = getattr(self, "_content_host", None)
            if host is not None and host.isVisible():
                # Use Auto section's focus_first with visible reason
                sec = getattr(self, "_help_content_section", None)
                if sec is not None:
                    try:
                        if sec.focus_first(reason=__import__('PySide6.QtCore', fromlist=['Qt']).Qt.FocusReason.OtherFocusReason):
                            return
                    except Exception:
                        pass
            # Fallback to sidebar
            if self.nav_widget.isVisible() and self.nav_widget.count() > 0:
                btn = self.nav_widget.current_row_button() or self.nav_widget.row_button(0)
                if btn is not None and isValid(btn):
                    btn.setFocus(__import__('PySide6.QtCore', fromlist=['Qt']).Qt.FocusReason.OtherFocusReason)
                    return
            # Last fallback to search field
            if self._search_field.isVisible():
                self._search_field.setFocus(__import__('PySide6.QtCore', fromlist=['Qt']).Qt.FocusReason.OtherFocusReason)
        except Exception:
            pass

    def _scroll_to_anchor(self, anchor: str) -> None:
        widget = self._document.scroll_to_anchor(anchor)
        if widget is not None:
            self._scroll.ensureWidgetVisible(widget, 0, 24)

    def _sync_sidebar(self) -> None:
        if self._search_mode:
            # A live search owns the sidebar; navigation must not rebuild the
            # sibling tree under it. clear_topic_search() restores the tree.
            return
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
                item.setSizeHint(QSize(0, scaled_px(35)))
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
