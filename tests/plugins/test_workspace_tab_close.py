"""Closing the only workspace tab exits the application."""

from types import SimpleNamespace

from ui.presenters.main_window.workspace import (
    on_workspace_tab_close_requested,
)


class _Window:
    def __init__(self) -> None:
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


class _SessionManager:
    def __init__(self, count: int) -> None:
        self._sessions = [object() for _ in range(count)]

    def list_sessions(self):
        return list(self._sessions)


def test_closing_only_workspace_tab_closes_main_window():
    window = _Window()
    workspace = SimpleNamespace(close_workspace_session=lambda _session_id: None)
    presenter = SimpleNamespace(
        main_window_app=window,
        session_manager=_SessionManager(1),
        main_controller=SimpleNamespace(workspace=workspace),
        ui=SimpleNamespace(
            workspace_tabs=SimpleNamespace(tabData=lambda _index: "only-session")
        ),
    )

    on_workspace_tab_close_requested(presenter, 0)

    assert window.close_calls == 1
