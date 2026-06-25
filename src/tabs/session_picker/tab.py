"""New-session picker tab contract implementation."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QWidget

from tabs.contract import TabContext, TabContract
from tabs.session_picker.widget import SessionPickerWidget


class SessionPickerTab(TabContract):
    @property
    def session_type(self) -> str:
        return "session_picker"

    @property
    def display_name(self) -> str:
        return "New Tab"

    @property
    def resources_dir(self) -> Path | None:
        return Path(__file__).parent / "resources"

    @property
    def i18n_namespace(self) -> str | None:
        return "session_picker"

    def create_page(self, parent: QWidget, context: TabContext) -> QWidget:
        return SessionPickerWidget(parent, context=context)
