"""Closing the only workspace tab falls back to the session picker instead
of exiting the application (see on_workspace_tab_close_requested)."""

from types import SimpleNamespace

from ui.presenters.main_window.workspace import (
    on_workspace_tab_close_requested,
)


class _SessionManager:
    def __init__(self, count: int) -> None:
        self._sessions = [object() for _ in range(count)]

    def list_sessions(self):
        return list(self._sessions)


def test_closing_only_workspace_tab_opens_session_picker_then_closes_it():
    calls = []
    workspace = SimpleNamespace(
        replace_workspace_session=lambda session_type, closing_session_id: calls.append(
            ("replace", session_type, closing_session_id)
        ),
        close_workspace_session=lambda session_id: calls.append(
            ("close", session_id)
        ),
    )
    presenter = SimpleNamespace(
        session_manager=_SessionManager(1),
        main_controller=SimpleNamespace(workspace=workspace),
        ui=SimpleNamespace(
            workspace_tabs=SimpleNamespace(tabData=lambda _index: "only-session")
        ),
    )

    on_workspace_tab_close_requested(presenter, 0)

    # One atomic replacement, not create+close: the strip never holds both
    # tabs for an intermediate frame.
    assert calls == [("replace", "session_picker", "only-session")]


def test_closing_tab_with_more_than_one_session_just_closes_it():
    calls = []
    workspace = SimpleNamespace(
        replace_workspace_session=lambda session_type, closing_session_id: calls.append(
            ("replace", session_type, closing_session_id)
        ),
        close_workspace_session=lambda session_id: calls.append(
            ("close", session_id)
        ),
    )
    presenter = SimpleNamespace(
        session_manager=_SessionManager(2),
        main_controller=SimpleNamespace(workspace=workspace),
        ui=SimpleNamespace(
            workspace_tabs=SimpleNamespace(tabData=lambda _index: "some-session")
        ),
    )

    on_workspace_tab_close_requested(presenter, 0)

    assert calls == [("close", "some-session")]


def test_closing_replacement_failure_is_logged_not_crashing():
    workspace = SimpleNamespace(
        replace_workspace_session=lambda session_type, closing_session_id: (_ for _ in ()).throw(
            RuntimeError("create failed")
        ),
        close_workspace_session=lambda session_id: None,
    )
    presenter = SimpleNamespace(
        session_manager=_SessionManager(1),
        main_controller=SimpleNamespace(workspace=workspace),
        ui=SimpleNamespace(
            workspace_tabs=SimpleNamespace(tabData=lambda _index: "only-session")
        ),
    )

    # Must not raise: a failed picker creation should be logged and the close
    # handler must stay usable.
    on_workspace_tab_close_requested(presenter, 0)