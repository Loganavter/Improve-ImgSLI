"""New-session picker tab contract implementation."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QWidget

from tabs.contract import TabContext, TabContract
from tabs.session_picker.widget import SessionPickerWidget


class SessionPickerTab(TabContract):
    startup_tier = "bootstrap"

    @property
    def session_type(self) -> str:
        return "session_picker"

    @property
    def display_name(self) -> str:
        return "New Tab"

    def localized_display_name(self, language: str) -> str:
        from sli_ui_toolkit.i18n import tr

        key = "session_picker.tab_name"
        translated = tr(key, language)
        return translated if translated != key else self.display_name

    @property
    def resources_dir(self) -> Path | None:
        return Path(__file__).parent / "resources"

    @property
    def i18n_namespace(self) -> str | None:
        return "session_picker"

    def create_page(self, parent: QWidget, context: TabContext) -> QWidget:
        return SessionPickerWidget(parent, context=context)

    def create_service(self, service_id: str, *args, **kwargs):
        if service_id == "session_picker.host_chrome":
            from tabs.registry import TabRegistry
            from tabs.session_picker.host_chrome import SessionPickerHostChromeAdapter

            page = TabRegistry().get_page(self.session_type)
            if page is None:
                return None
            return SessionPickerHostChromeAdapter(page)
        return None

    def apply_host_session_mode(self, ui, session_title: str | None = None) -> bool:
        return True
