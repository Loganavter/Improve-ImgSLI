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
        create_workspace_session=lambda session_type, activate: calls.append(
            ("create", session_type, activate)
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

    assert calls == [
        ("create", "session_picker", True),
        ("close", "only-session"),
    ]
