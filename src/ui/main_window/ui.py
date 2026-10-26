import logging

from PySide6.QtWidgets import (
    QStackedWidget,
    QWidget,
)

from resources.translations import tr
from ui.icon_manager import AppIcon
from ui.main_window.layouts import LayoutComposer
from ui.widgets.workspace_tab_strip import WorkspaceTabStrip
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


def _widget_in_content_subtree(widget, content) -> bool:
    """True when ``widget`` renders inside the below-strip content area.

    Toast anchors must be tab-owned canvas widgets (inside
    ``workspace_content_widget``), never the window itself: a window-level
    anchor would let toasts overlap the tab strip. Fail-open (True) for
    non-widget doubles and when the content host is not built yet.
    """
    if content is None or not hasattr(content, "parentWidget"):
        return True
    if widget is None or not hasattr(widget, "parentWidget"):
        return True
    node = widget
    for _ in range(100):
        if node is content:
            return True
        try:
            node = node.parentWidget()
        except RuntimeError:
            return False
        if node is None:
            return False
    return False


def enable_workspace_tab_reordering(strip) -> bool:
    """Turn on drag-to-reorder for the workspace tab strip. Default ON.

    Tab reordering is a basic tab-strip affordance, so the app switches it on
    unconditionally (no setting, no "enable" step) — ``AdaptiveTabStrip`` ships
    it off so that a host which never asks keeps a click-only strip.

    Guarded on purpose: the app may run against a released ``sli-ui-toolkit``
    that predates ``setMovable``. Then the strip keeps exactly today's
    click-only behaviour instead of raising at startup. Returns True when the
    strip accepted the call.
    """
    if strip is None or not hasattr(strip, "setMovable"):
        logger.debug(
            "workspace tab strip: %s has no setMovable — drag reorder stays off",
            type(strip).__name__,
        )
        return False
    try:
        strip.setMovable(True)
    except Exception:
        logger.debug(
            "workspace tab strip: setMovable(True) failed", exc_info=True
        )
        return False
    return True


class Ui_ImageComparisonApp:
    """Owns widget construction and exposes the update API used by the presenter.

    Layout assembly is delegated to LayoutComposer (ui/main_window/layouts.py).
    """

    def setupUi(self, main_window: QWidget):
        self.main_window = main_window
        from resources.translations import emit_language_changed

        emit_language_changed(self._current_language())
        self._create_static_widgets(main_window)
        self._layout = LayoutComposer(self)
        self._layout.build(main_window)
        from ui.main_window.translations import install_translations

        install_translations(self)

    def _create_static_widgets(self, main_window: QWidget):
        self.workspace_tabs = WorkspaceTabStrip(
            add_icon=AppIcon.ADD,
            close_icon=AppIcon.CLOSE,
            parent=main_window,
        )
        self.btn_new_session = self.workspace_tabs.add_button
        enable_workspace_tab_reordering(self.workspace_tabs)
        self.workspace_stack = QStackedWidget(main_window)
        self._tab_registry = None
        self.legacy_tab_widgets: dict = {}
        # True while ``sync_workspace_tabs`` restores the saved order: those
        # programmatic ``moveTab`` calls must not be reported as a user drag
        # (see ``ui.presenters.main_window.workspace_tab_order``).
        self._restoring_tab_order = False

    def _current_language(self) -> str:
        try:
            store = getattr(self.main_window, "store", None)
            if store is None:
                return "en"
            return store.settings.current_language
        except AttributeError:
            return "en"

    def sync_workspace_tabs(self, sessions, active_session_id):
        tabs = self.workspace_tabs
        language = self._current_language()
        # Restoring the saved order is not a user drag: while this flag is set
        # the ``tabMoved`` persistence hook leaves the store alone, so a
        # rebuild can never write an intermediate strip order back.
        self._restoring_tab_order = True
        tabs.blockSignals(True)
        try:
            sessions = list(sessions)
            desired_ids = [getattr(session, "id", None) for session in sessions]
            self._drop_stale_workspace_tabs(tabs, desired_ids)

            active_index = -1
            for position, session in enumerate(sessions):
                tab_text = self._localized_session_title(session, language)
                # Identity, not position: the strip and the store may disagree
                # after a close/create, and a tab must never be renamed into
                # another session just because it sits at the same index.
                index = self._workspace_tab_index(tabs, session.id)
                if index < 0:
                    tabs.insertTab(position, tab_text)
                    index = position
                elif index != position:
                    # Restore the persisted order (saved in the session list
                    # order, which is what a project file writes/reads).
                    tabs.moveTab(index, position)
                if tabs.tabText(index) != tab_text:
                    tabs.setTabText(index, tab_text)
                if tabs.tabData(index) != session.id:
                    tabs.setTabData(index, session.id)
                if session.id == active_session_id:
                    active_index = position

            if active_index >= 0 and tabs.currentIndex() != active_index:
                tabs.setCurrentIndex(active_index)
            tabs.refresh_close_buttons()
        finally:
            tabs.blockSignals(False)
            self._restoring_tab_order = False

    @staticmethod
    def _workspace_tab_index(tabs, session_id) -> int:
        """Index of the tab that owns *session_id* (``-1`` when absent)."""
        if not session_id:
            return -1
        for index in range(tabs.count()):
            if tabs.tabData(index) == session_id:
                return index
        return -1

    @staticmethod
    def _drop_stale_workspace_tabs(tabs, desired_ids) -> None:
        """Remove tabs whose session is gone.

        A closed session's tab must disappear instead of being reused for
        whatever session lands on the same index next.
        """
        wanted = {session_id for session_id in desired_ids if session_id}
        for index in range(tabs.count() - 1, -1, -1):
            if tabs.tabData(index) not in wanted:
                tabs.removeTab(index)

    def _localized_session_title(self, session, language: str) -> str:
        from domain.workspace import WorkspaceState

        title = getattr(session, "title", "") or ""
        session_type = getattr(session, "session_type", "")
        if not WorkspaceState.is_auto_title(title, session_type):
            return title
        return self._localized_session_type_label(session_type, language)

    def _localized_session_type_label(self, session_type: str, language: str) -> str:
        tab_registry = getattr(self, "_tab_registry", None)
        if tab_registry is not None:
            tab = tab_registry.get_tab(session_type)
            if tab is not None:
                localized = tab.localized_display_name(language)
                if localized and localized != session_type:
                    return localized
        key = f"workspace.session_types.{session_type}"
        translated = tr(key, language)
        return session_type if translated == key else translated

    def sync_session_mode(self, session_type: str, session_title: str | None = None):
        if self._tab_registry:
            self._tab_registry.activate(session_type)
        tab_page = (
            self._tab_registry.get_page(session_type) if self._tab_registry else None
        )
        if tab_page is not None:
            self.workspace_stack.setCurrentWidget(tab_page)
            if self._tab_registry:
                # Theme may have flipped while this page was hidden.
                main_window = self.workspace_stack.window()
                self._tab_registry.flush_stale_appearance(main_window)
                # Toasts are one shared host-owned manager; repoint it at
                # the newly active tab's own canvas instead of leaving it
                # anchored to whichever tab last claimed it.
                toast_manager = getattr(main_window, "toast_manager", None)
                if toast_manager is not None:
                    anchor = self._tab_registry.create_service("toast_anchor_widget")
                    if anchor is not None:
                        # Content-below-strip: the anchor comes only from the
                        # active tab's own canvas via create_service — never
                        # window-parented. Refuse anything outside the
                        # below-strip content subtree so toasts can't cover
                        # the tab strip.
                        content = getattr(
                            self, "workspace_content_widget", None
                        )
                        if _widget_in_content_subtree(anchor, content):
                            toast_manager.set_anchor(anchor)
                        else:
                            logger.warning(
                                "sync_session_mode(%r): toast anchor outside "
                                "workspace content — keeping previous anchor "
                                "(anchor=%r)",
                                session_type,
                                type(anchor).__name__,
                            )

        handled = (
            self._tab_registry.apply_host_session_mode(
                session_type,
                self,
                session_title=session_title,
            )
            if self._tab_registry
            else False
        )
        if not handled:
            # Not a fault: a tab may legitimately have no host chrome to apply
            # (``TabContract.apply_host_session_mode`` defaults to False). Keep
            # it at debug so a normal session does not log a WARNING on every
            # open/switch.
            logger.debug(
                "sync_session_mode(%r): no tab claimed apply_host_session_mode",
                session_type,
            )
