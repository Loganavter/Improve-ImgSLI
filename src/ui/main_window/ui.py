import logging

from PySide6.QtWidgets import (
    QStackedWidget,
    QWidget,
)

from resources.translations import tr
from ui.icon_manager import AppIcon
from ui.main_window.layouts import LayoutComposer
from ui.widgets.workspace_tab_strip import WorkspaceTabStrip

logger = logging.getLogger("ImproveImgSLI")

_SESSION_TYPE_KEYS = {
    "multi_compare": "workspace.session_types.multi_compare",
    "session_picker": "workspace.session_types.session_picker",
}


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
        self.workspace_stack = QStackedWidget(main_window)
        self._tab_registry = None
        self.legacy_tab_widgets = {}

    def _current_language(self) -> str:
        try:
            return self.main_window.store.settings.current_language
        except AttributeError:
            return "en"

    def sync_workspace_tabs(self, sessions, active_session_id):
        tabs = self.workspace_tabs
        language = self._current_language()
        tabs.blockSignals(True)
        try:
            sessions = list(sessions)
            target_count = len(sessions)

            while tabs.count() > target_count:
                tabs.removeTab(tabs.count() - 1)

            active_index = -1
            for index, session in enumerate(sessions):
                tab_text = self._localized_session_title(session, language)
                session_type_label = self._localized_session_type_label(
                    session.session_type,
                    language,
                )
                tooltip = f"{tab_text} [{session_type_label}]"
                if index < tabs.count():
                    if tabs.tabText(index) != tab_text:
                        tabs.setTabText(index, tab_text)
                    if tabs.tabData(index) != session.id:
                        tabs.setTabData(index, session.id)
                    tabs.setTabToolTip(index, tooltip)
                else:
                    tabs.addTab(tab_text)
                    tabs.setTabData(index, session.id)
                    tabs.setTabToolTip(index, tooltip)
                if session.id == active_session_id:
                    active_index = index

            if active_index >= 0 and tabs.currentIndex() != active_index:
                tabs.setCurrentIndex(active_index)
            tabs.refresh_close_buttons()
        finally:
            tabs.blockSignals(False)

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
        key = _SESSION_TYPE_KEYS.get(session_type)
        if key is None:
            return session_type
        translated = tr(key, language)
        return session_type if translated == key else translated

    def sync_session_mode(self, session_type: str, session_title: str | None = None):
        tab_page = (
            self._tab_registry.get_page(session_type) if self._tab_registry else None
        )
        if tab_page is not None:
            self.workspace_stack.setCurrentWidget(tab_page)
            if self._tab_registry:
                self._tab_registry.activate(session_type)

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
            logger.warning(
                "sync_session_mode(%r): no tab claimed apply_host_session_mode",
                session_type,
            )

