"""Smoke test: app-shell navigation sections register in the right order.

``core.app_shell_navigation.register_app_shell_navigation`` is the single
source of truth for the top-to-bottom section ordering that
``_neighbor()`` relies on.  This test asserts the three registrations
happen in order (title bar → tab strip → session picker) so a future
edit can't silently reorder them without breaking vertical section
traversal.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QWidget


def test_app_shell_navigation_registers_in_order(qtbot):
    """Title bar, tab strip, session picker — in that order."""
    from core.app_shell_navigation import register_app_shell_navigation

    window = MagicMock()
    window.ui.workspace_tabs = MagicMock()

    calls: list[str] = []

    def _track_register(owner, section):
        calls.append(getattr(section, "_name", type(section).__name__))

    mock_nav = MagicMock()
    mock_nav.register.side_effect = _track_register

    with patch(
        "sli_ui_toolkit.managers.NavigationManager"
    ) as MockNavManager, patch(
        "ui.main_window.title_bar_navigation.TitleBarNavigationSection",
        side_effect=lambda tb: MagicMock(_name="title_bar"),
    ), patch(
        "core.navigation_sections.TabStripSection",
        side_effect=lambda ts: MagicMock(_name="tab_strip"),
    ), patch(
        "core.navigation_sections.SessionPickerSection",
        side_effect=lambda pg: MagicMock(_name="session_picker"),
    ), patch(
        "tabs.registry.TabRegistry"
    ) as MockTabRegistry:
        MockNavManager.get_instance.return_value = mock_nav
        # TabRegistry().get_page() must return something for session picker.
        MockTabRegistry.return_value.get_page.return_value = MagicMock()

        register_app_shell_navigation(window)

    assert calls == ["title_bar", "tab_strip", "session_picker"], (
        f"sections must register top-to-bottom; got {calls}"
    )
