"""Settings select_section and Help show_dialog(page=) deep-link plumbing."""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from plugins.help.plugin import HelpPlugin
from plugins.settings.dialog import SettingsDialog


def test_settings_dialog_select_section_by_id():
    QApplication.instance() or QApplication([])
    dialog = SettingsDialog(
        current_language="en",
        current_theme="dark",
        current_max_length=30,
        min_limit=1,
        max_limit=200,
        debug_mode_enabled=False,
        system_notifications_enabled=True,
        current_resolution_limit=0,
        active_tab="image_compare",
    )
    assert dialog.sidebar.currentRow() == 0

    dialog.select_section("builtin.interface")
    assert dialog.sidebar.currentRow() == 1

    dialog.select_section("image_compare.analysis")
    sections = dialog._active_sections
    expected = next(
        i for i, section in enumerate(sections) if section.section_id == "image_compare.analysis"
    )
    assert dialog.sidebar.currentRow() == expected

    dialog.select_section("does.not.exist")
    assert dialog.sidebar.currentRow() == expected


def test_help_plugin_show_dialog_navigates_to_page(monkeypatch):
    navigated: list[tuple[str, str | None]] = []

    class FakeHelpDialog:
        def __init__(self, *, current_language="en", app_name="", parent=None):
            self.current_language = current_language
            self.app_name = app_name
            self._parent = parent
            self.destroyed = SimpleNamespace(connect=lambda *_a, **_k: None)

        def update_language(self, language: str) -> None:
            self.current_language = language

        def parent(self):
            return self._parent

        def setParent(self, parent) -> None:
            self._parent = parent

        def show(self) -> None:
            return None

        def raise_(self) -> None:
            return None

        def activateWindow(self) -> None:
            return None

        def navigate_to(self, slug: str, anchor: str | None = None) -> None:
            navigated.append((slug, anchor))

    monkeypatch.setattr("plugins.help.plugin.HelpDialog", FakeHelpDialog)

    plugin = HelpPlugin()
    plugin.show_dialog(language="en", page="magnifier", anchor="overview")
    assert navigated == [("magnifier", "overview")]

    plugin.show_dialog(language="en")
    assert navigated == [("magnifier", "overview")]
