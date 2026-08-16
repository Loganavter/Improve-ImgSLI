"""Hierarchical help dialog: hubs, back bar, HelpDocumentView pages."""

from __future__ import annotations

import logging
from functools import lru_cache

from PySide6.QtCore import QEvent, QObject, QSize, QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QMouseEvent, QShortcut
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
from plugins.help.icons import resolve_help_icon
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
from sli_ui_toolkit.ui.widgets.composite.help_document import (
    blocks_to_plain_text,
    parse_help_blocks,
)
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

logger = logging.getLogger("ImproveImgSLI")


@lru_cache(maxsize=512)
def _page_search_text(language: str, body_rel: str, body_root) -> str:
    """Cached plain text of a help page body (what the canvas renders).

    Mirrors ``HelpDocumentView`` block parsing so the search haystack is
    exactly the text ``scroll_to_text`` can highlight afterwards.
    """
    md = read_help_page_markdown(language, body_rel, body_root=body_root)
    return blocks_to_plain_text(parse_help_blocks(md))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


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
        self._render_current()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._install_mouse_nav_filter()

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

        self.shell = SidebarDialogShell(
            sidebar_width=HELP_SIDEBAR_DEFAULT_WIDTH,
            content_margins=(0, 0, 0, 0),
            content_spacing=0,
            sidebar_header=self._search_field,
        )
        self.nav_widget = self.shell.sidebar
        self.nav_widget.enable_minimal_scrollbar()
        self.nav_widget.setMinimumWidth(scaled_px(HELP_SIDEBAR_MIN_WIDTH))
        self.nav_widget.setMaximumWidth(scaled_px(HELP_SIDEBAR_MAX_WIDTH))
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

    def _setup_topic_search(self) -> None:
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(120)
        self._search_timer.timeout.connect(self._apply_topic_search)
        self._search_field.textChanged.connect(self._on_search_text_changed)
        self._search_escape = QShortcut(
            QKeySequence(Qt.Key.Key_Escape), self._search_field
        )
        self._search_escape.activated.connect(self.clear_topic_search)

    def _on_search_text_changed(self, _text: str) -> None:
        if self._search_timer.isActive():
            self._search_timer.stop()
        self._search_timer.start()

    def _apply_topic_search(self) -> None:
        query = self._search_field.text().strip()
        if not query:
            self.clear_topic_search()
            return
        matches = self._rank_topic_matches(query)
        self._search_mode = True
        #: node ids whose best match came from page content (vs title) — those
        #: results open at the first occurrence with a text highlight.
        self._search_body_match_ids = {
            node_id for node_id, _score, in_body in matches if in_body
        }
        self.nav_widget.clear()
        if not matches:
            self.nav_widget.add_item(
                tr("help.search_no_results", language=self.current_language),
                row_height=scaled_px(35),
            )
            self._set_sidebar_expanded(True)
            return
        for node_id, _score, _in_body in matches[:12]:
            node = self._tree.require(node_id)
            self.nav_widget.add_item(
                node_title(node, self.current_language),
                icon=resolve_help_icon(
                    node.icon, resolvers=self._tree.icon_resolvers
                ),
                data=node_id,
                row_height=scaled_px(35),
            )
        self._set_sidebar_expanded(True)
        self.nav_widget.setCurrentRow(-1)

    def _rank_topic_matches(self, query: str) -> list[tuple[str, int, bool]]:
        from sli_ui_toolkit.ui.widgets.comboboxes._search import (
            match_score_normalized,
            normalize_for_search,
        )

        # Match against the current language AND English (Find Action-style
        # cross-language haystacks): a query typed before a language switch —
        # or in a language the topic isn't translated into — still hits.
        langs = ("en", self.current_language) if self.current_language != "en" else ("en",)
        norm_query = normalize_for_search(query)
        scored: list[tuple[int, str, bool]] = []
        for node_id, node in self._tree.nodes.items():
            if node_id == self._tree.root_id:
                continue
            best: int | None = None
            in_body = False
            for lang in langs:
                title = node_title(node, lang)
                if title:
                    score = match_score_normalized(
                        norm_query, normalize_for_search(title)
                    )
                    if score is not None and (best is None or score < best):
                        best = score
                        in_body = False
                if node.kind == "page" and node.body:
                    # Non-fuzzy by default: only real locatable occurrences
                    # rank for content matches, so the canvas can always
                    # scroll to and highlight them.
                    norm_body = _page_search_norm_text(
                        lang, node.body, node.body_root
                    )
                    score = match_score_normalized(norm_query, norm_body)
                    if score is not None and (best is None or score < best):
                        best = score
                        in_body = True
            if best is not None:
                scored.append((best, node_id, in_body))
        scored.sort(key=lambda item: (item[0], item[1]))
        return [(node_id, score, in_body) for score, node_id, in_body in scored]

    def _on_search_result_activated(self, row: int) -> None:
        item = self.nav_widget.item(row)
        if item is None:
            return
        node_id = item.data()
        if not node_id:
            return
        self._pending_anchor = None
        self._nav.push(node_id)
        self._render_current()
        # Content matches jump to the first occurrence and highlight it;
        # title matches just open the page normally.
        if node_id in getattr(self, "_search_body_match_ids", ()):
            query = self._search_field.text().strip()
            if query:
                target = self._document.scroll_to_text(query)
                if target is not None:
                    self._scroll.ensureWidgetVisible(target, 0, 24)

    def clear_topic_search(self) -> None:
        if not self._search_mode:
            return
        self._search_mode = False
        if self._search_field.text():
            self._search_field.blockSignals(True)
            self._search_field.clear()
            self._search_field.blockSignals(False)
        self._sync_sidebar()

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