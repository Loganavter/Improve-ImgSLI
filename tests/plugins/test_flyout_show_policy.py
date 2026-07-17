"""App flyout show policy: context menus coexist; pickers stay exclusive."""

from __future__ import annotations

from sli_ui_toolkit.managers import FlyoutManager, GroupShowPolicy

from ui.flyout_policy import install_flyout_show_policy
from ui.widgets.font_settings_flyout import FontSettingsFlyout


def test_install_flyout_show_policy_configures_context_menu_coexistence():
    manager = FlyoutManager.get_instance()
    previous = manager.show_policy()
    try:
        policy = install_flyout_show_policy()
        assert isinstance(policy, GroupShowPolicy)
        assert manager.show_policy() is policy

        menu = type("M", (), {"flyout_group": "context_menu"})()
        listing = type("L", (), {"flyout_group": "unified_list"})()
        options = type("O", (), {"flyout_group": "options"})()
        font = type("F", (), {"flyout_group": "font_settings"})()

        assert policy.should_dismiss(menu, listing) is False
        assert policy.should_claim_active(menu, listing) is False
        # List refresh/open must not dismiss an open context menu.
        assert policy.should_dismiss(listing, menu) is False
        # Interp / font flyouts dismiss the list and each other.
        assert policy.should_dismiss(options, listing) is True
        assert policy.should_dismiss(font, options) is True
        assert policy.should_dismiss(listing, font) is True
    finally:
        manager.set_show_policy(previous)


def test_font_settings_flyout_group_and_registration(qapp):
    from PySide6.QtWidgets import QWidget

    assert FontSettingsFlyout.flyout_group == "font_settings"
    manager = FlyoutManager.get_instance()
    host = QWidget()
    host.resize(320, 240)
    host.show()
    flyout = FontSettingsFlyout(host)
    assert flyout in manager._registered_flyouts
    flyout.deleteLater()
    host.deleteLater()
