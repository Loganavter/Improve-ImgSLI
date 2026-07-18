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


def test_title_bar_resize_keeps_context_menu_flyouts(qapp):
    """Host Resize must not close File/Help (context_menu) after policy install."""
    from sli_ui_toolkit.ui.windows.custom_title_bar import CustomTitleBar
    from ui import flyout_policy

    class _FakeFlyout:
        def __init__(self, group: str) -> None:
            self.flyout_group = group
            self._visible = True

        def isVisible(self) -> bool:
            return self._visible

        def hide(self) -> None:
            self._visible = False

    manager = FlyoutManager.get_instance()
    previous = manager.show_policy()
    previous_hide = CustomTitleBar._hide_active_flyouts
    previous_patched = flyout_policy._TITLE_BAR_RESIZE_PATCHED
    previous_registered = set(getattr(manager, "_registered_flyouts", ()))
    previous_active = getattr(manager, "_active_flyout", None)
    try:
        # Force re-eval: simulate stock 3.1.1 close_all Resize path.
        def _stock_close_all(self) -> None:
            FlyoutManager.get_instance().close_all()

        CustomTitleBar._hide_active_flyouts = _stock_close_all
        flyout_policy._TITLE_BAR_RESIZE_PATCHED = False
        install_flyout_show_policy()
        assert flyout_policy._TITLE_BAR_RESIZE_PATCHED is True

        menu = _FakeFlyout("context_menu")
        other = _FakeFlyout("options")
        manager._registered_flyouts = {menu, other}
        manager._active_flyout = menu

        CustomTitleBar()._hide_active_flyouts()

        assert menu.isVisible()
        assert not other.isVisible()
        assert manager._active_flyout is menu
    finally:
        manager.set_show_policy(previous)
        CustomTitleBar._hide_active_flyouts = previous_hide
        flyout_policy._TITLE_BAR_RESIZE_PATCHED = previous_patched
        manager._registered_flyouts = previous_registered
        manager._active_flyout = previous_active


def test_button_suppress_click_clears_context_menu_flag(qapp):
    """Suppressed click must not leave ``_suppress_next_context_menu`` for next open."""
    from sli_ui_toolkit.ui.widgets.buttons.button import Button
    from ui import flyout_policy

    previous_emit = Button._emit_click_signals
    previous_patched = flyout_policy._BUTTON_SUPPRESS_PATCHED
    try:
        # Simulate stock 3.1.1 emit that only clears the click flag.
        def _stock_emit(self) -> None:
            if getattr(self, "_suppress_next_click", False):
                self._suppress_next_click = False
                return
            self.clicked.emit()

        Button._emit_click_signals = _stock_emit
        flyout_policy._BUTTON_SUPPRESS_PATCHED = False
        install_flyout_show_policy()
        assert flyout_policy._BUTTON_SUPPRESS_PATCHED is True

        button = Button("File")
        button._suppress_next_click = True
        button._suppress_next_context_menu = True
        clicks: list[int] = []
        button.clicked.connect(lambda: clicks.append(1))

        button._emit_click_signals()
        assert clicks == []
        assert getattr(button, "_suppress_next_click", False) is False
        assert getattr(button, "_suppress_next_context_menu", False) is False

        button._emit_click_signals()
        assert clicks == [1]
        button.deleteLater()
    finally:
        Button._emit_click_signals = previous_emit
        flyout_policy._BUTTON_SUPPRESS_PATCHED = previous_patched


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
