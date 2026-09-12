"""Help dialog must construct — AppIcon.HELP used to be missing and failed silently."""

from __future__ import annotations

from plugins.help.plugin import HelpPlugin
from ui.icon_manager import AppIcon, get_app_icon


def test_app_icon_help_resolves():
    assert AppIcon.HELP.value == "help.svg"
    icon = get_app_icon(AppIcon.HELP)
    assert not icon.isNull()


def test_help_plugin_show_dialog_opens(qtbot):
    plugin = HelpPlugin()
    plugin.show_dialog(parent=None, language="en", page="hotkeys")
    assert plugin._dialog is not None
    qtbot.addWidget(plugin._dialog)
    assert plugin._dialog.isVisible()
    assert plugin._dialog._nav.current_id == "platform.hotkeys"


def test_help_dialog_stays_parentless_when_main_window_passed(qtbot):
    """Help must not be transient-for MainWindow (buries Video Editor / Export)."""
    from PySide6.QtWidgets import QWidget

    host = QWidget()
    qtbot.addWidget(host)
    plugin = HelpPlugin()
    plugin.show_dialog(parent=host, language="en")
    assert plugin._dialog is not None
    qtbot.addWidget(plugin._dialog)
    assert plugin._dialog.parent() is None
