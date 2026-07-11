"""The add-tab button opens the session picker directly and carries no
session-type dropdown menu (see configure_workspace_actions)."""

from types import SimpleNamespace

from ui.presenters.main_window.workspace import configure_workspace_actions


class _Button:
    def __init__(self):
        self.actions = None

    def set_actions(self, actions):
        self.actions = actions


def test_configure_workspace_actions_clears_new_session_button_menu():
    button = _Button()
    presenter = SimpleNamespace(ui=SimpleNamespace(btn_new_session=button))

    configure_workspace_actions(presenter)

    assert button.actions == []
