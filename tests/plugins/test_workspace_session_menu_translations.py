"""The add-tab button opens the session picker directly (see configure_workspace_actions)."""

from types import SimpleNamespace

from ui.presenters.main_window.workspace import configure_workspace_actions


def test_configure_workspace_actions_is_noop_for_new_session_button():
    button = object()
    presenter = SimpleNamespace(ui=SimpleNamespace(btn_new_session=button))

    configure_workspace_actions(presenter)

    assert presenter.ui.btn_new_session is button
