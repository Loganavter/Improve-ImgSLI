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
    plugin.show_dialog(parent=None, language="en", page="platform.hotkeys")
    assert plugin._dialog is not None
    qtbot.addWidget(plugin._dialog)
    assert plugin._dialog.isVisible()
    assert plugin._dialog._nav.current_id == "platform.hotkeys"


def test_help_dialog_parents_to_main_window(qtbot):
    """Help is transient-for the calling window (xdg-activation exemption)."""
    from PySide6.QtWidgets import QWidget

    host = QWidget()
    qtbot.addWidget(host)
    plugin = HelpPlugin()
    plugin.show_dialog(parent=host, language="en")
    assert plugin._dialog is not None
    # NOTE: only the host is qtbot-owned — the parented dialog is destroyed
    # with it at teardown (a second explicit close would double-free).
    assert plugin._dialog.isVisible()
    assert plugin._dialog.parent() is host


def _open_help_with_modality(qtbot, host, *, keyboard: bool):
    """Open the help dialog as a mouse click / keypress would.

    ``host`` is owned by the caller: pytest-qt keeps only a weak reference to
    added widgets, and a parented dialog dies with its host.
    """
    from sli_ui_toolkit.managers import NavigationManager

    mgr = NavigationManager.get_instance()
    mgr._last_input_keyboard = keyboard
    plugin = HelpPlugin()
    plugin.show_dialog(parent=host, language="en")
    assert plugin._dialog is not None
    dialog = plugin._dialog
    # Both deferred focus timers (0 ms and 60 ms) must have run: the ring was
    # painted by the section bootstrap they kick off.
    qtbot.wait(150)
    return plugin, dialog, mgr


def _ringed_widgets(dialog):
    """Widgets that actually paint the keyboard ring (FocusLayer.applies)."""
    from PySide6.QtWidgets import QWidget

    return [
        widget
        for widget in dialog.findChildren(QWidget)
        if getattr(widget, "_keyboard_focus", False) and widget.hasFocus()
    ]


def test_help_open_from_mouse_shows_no_focus_ring(qtbot):
    """A mouse-opened help window must not paint the ring on its first card.

    Regression (2026-10-22): the dialog forced ``_last_input_keyboard = True``,
    so the deferred container focus + ``AutoNavigationSection`` bootstrap
    granted ``OtherFocusReason`` and the "About" card came up ringed after a
    plain menu click — the keyboard-only affordance showed on a mouse gesture
    (same class as inv-flyout-focus-mouse).
    """
    from PySide6.QtWidgets import QWidget

    host = QWidget()
    qtbot.addWidget(host)
    _plugin, dialog, mgr = _open_help_with_modality(qtbot, host, keyboard=False)
    assert mgr.last_input_was_keyboard() is False, (
        "the help dialog overwrote the input modality — a later programmatic "
        "setFocus then grants OtherFocusReason (ring) after a mouse click"
    )
    assert _ringed_widgets(dialog) == [], "keyboard ring painted on a mouse open"


def test_help_open_from_keyboard_keeps_ring_modality(qtbot):
    """The keyboard path must stay keyboard: only the mouse path lost its flag."""
    from PySide6.QtWidgets import QWidget

    host = QWidget()
    qtbot.addWidget(host)
    _plugin, _dialog, mgr = _open_help_with_modality(qtbot, host, keyboard=True)
    assert mgr.last_input_was_keyboard() is True