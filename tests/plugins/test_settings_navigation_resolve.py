"""Settings Find-Action reveal resolvers must call the dialog with the right arity.

Red-before: ``settings_navigation.resolve_settings_group/member`` passed a
leading ``section_id`` to ``SettingsDialog.group_widget_for`` / ``member_widget_for``,
which take ``(group_key)`` / ``(group_key, member_key)`` — every reveal raised
``TypeError`` (caught + logged), so Find-Action "jump to setting" silently
returned ``None``.
"""

from __future__ import annotations


class _Dialog:
    def __init__(self) -> None:
        self.calls: dict[str, tuple] = {}

    def group_widget_for(self, group_key: str):
        self.calls["group"] = (group_key,)
        return "GROUP_WIDGET"

    def member_widget_for(self, group_key: str, member_key: str):
        self.calls["member"] = (group_key, member_key)
        return "MEMBER_WIDGET"


class _Dialogs:
    def __init__(self, dialog: _Dialog) -> None:
        self.settings_dialog = dialog


class _UI:
    def __init__(self, dialog: _Dialog) -> None:
        self.dialogs = _Dialogs(dialog)


class _Controller:
    def __init__(self, dialog: _Dialog) -> None:
        self._dialog = dialog

    def _ui_manager(self):
        return _UI(self._dialog)


def test_resolve_settings_member_uses_group_and_member_keys_only():
    from ui.main_window.use_cases import settings_navigation as sn

    dialog = _Dialog()
    ctl = _Controller(dialog)

    assert sn.resolve_settings_member(ctl, "group.section", "gkey", "mkey") == "MEMBER_WIDGET"
    assert dialog.calls["member"] == ("gkey", "mkey")


def test_resolve_settings_group_uses_group_key_only():
    from ui.main_window.use_cases import settings_navigation as sn

    dialog = _Dialog()
    ctl = _Controller(dialog)

    assert sn.resolve_settings_group(ctl, "group.section", "gkey") == "GROUP_WIDGET"
    assert dialog.calls["group"] == ("gkey",)
