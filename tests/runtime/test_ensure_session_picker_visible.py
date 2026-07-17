"""ensure_session_picker_visible reuses an open picker instead of duplicating."""

from __future__ import annotations

from types import SimpleNamespace

from core.store import INITIAL_WORKSPACE_SESSION_TYPE
from ui.presenters.main_window.workspace import ensure_session_picker_visible


class _FakeWorkspace:
    def __init__(self) -> None:
        self.created: list[str] = []
        self.switched: list[str] = []

    def create_workspace_session(self, session_type: str, activate: bool = True):
        self.created.append(session_type)
        return SimpleNamespace(id="new", session_type=session_type)

    def switch_workspace_session(self, session_id: str) -> bool:
        self.switched.append(session_id)
        return True


def test_ensure_session_picker_visible_reuses_existing():
    picker = SimpleNamespace(id="picker-1", session_type=INITIAL_WORKSPACE_SESSION_TYPE)
    other = SimpleNamespace(id="ic-1", session_type="image_compare")
    workspace = _FakeWorkspace()
    presenter = SimpleNamespace(
        main_controller=SimpleNamespace(workspace=workspace),
        session_manager=SimpleNamespace(
            list_sessions=lambda: (other, picker),
            get_active_session=lambda: other,
        ),
    )

    ensure_session_picker_visible(presenter)

    assert workspace.switched == ["picker-1"]
    assert workspace.created == []


def test_ensure_session_picker_visible_noop_when_already_active():
    picker = SimpleNamespace(id="picker-1", session_type=INITIAL_WORKSPACE_SESSION_TYPE)
    workspace = _FakeWorkspace()
    presenter = SimpleNamespace(
        main_controller=SimpleNamespace(workspace=workspace),
        session_manager=SimpleNamespace(
            list_sessions=lambda: (picker,),
            get_active_session=lambda: picker,
        ),
    )

    ensure_session_picker_visible(presenter)

    assert workspace.switched == []
    assert workspace.created == []


def test_ensure_session_picker_visible_creates_when_missing():
    workspace = _FakeWorkspace()
    presenter = SimpleNamespace(
        main_controller=SimpleNamespace(workspace=workspace),
        session_manager=SimpleNamespace(
            list_sessions=lambda: (
                SimpleNamespace(id="ic-1", session_type="image_compare"),
            ),
            get_active_session=lambda: None,
        ),
    )

    ensure_session_picker_visible(presenter)

    assert workspace.switched == []
    assert workspace.created == [INITIAL_WORKSPACE_SESSION_TYPE]
