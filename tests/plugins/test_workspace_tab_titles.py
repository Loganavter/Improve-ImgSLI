"""Workspace tab titles: canonical store value vs localized display."""

from types import SimpleNamespace
from unittest.mock import patch

from domain.workspace import WorkspaceState
from ui.presenters.main_window.workspace_tab_menu import (
    _title_for_storage,
    handle_workspace_tab_context_action,
)


def test_next_default_title_is_language_agnostic_without_number():
    state = WorkspaceState()
    assert state.next_default_title("session_picker") == "Session Picker"
    assert state.next_default_title("session_picker") == "Session Picker"
    assert state.next_default_title("image_compare") == "Image Compare"


def test_is_auto_title_detects_canonical_and_legacy_numbered_defaults():
    assert WorkspaceState.is_auto_title("Session Picker", "session_picker")
    assert WorkspaceState.is_auto_title("Session Picker 2", "session_picker")
    assert WorkspaceState.is_auto_title("Image Compare", "image_compare")
    assert not WorkspaceState.is_auto_title("Моя вкладка", "session_picker")
    assert not WorkspaceState.is_auto_title("Session Picker extra", "session_picker")


def test_title_for_storage_keeps_raw_when_localized_default_confirmed():
    session = SimpleNamespace(title="Session Picker", session_type="session_picker")
    presenter = SimpleNamespace(
        ui=SimpleNamespace(
            _localized_session_type_label=lambda _t, _lang: "Выбор сессии",
        )
    )
    stored = _title_for_storage(
        presenter,
        session,
        "Выбор сессии",
        "ru",
        display_title="Выбор сессии",
    )
    assert stored == "Session Picker"


def test_title_for_storage_strips_legacy_localized_number_to_bare_prefix():
    session = SimpleNamespace(title="Session Picker 2", session_type="session_picker")
    presenter = SimpleNamespace(
        ui=SimpleNamespace(
            _localized_session_type_label=lambda _t, _lang: "Выбор сессии",
        )
    )
    stored = _title_for_storage(
        presenter,
        session,
        "Выбор сессии 5",
        "ru",
        display_title="Выбор сессии",
    )
    assert stored == "Session Picker"


def test_title_for_storage_keeps_custom_user_text():
    session = SimpleNamespace(title="Session Picker", session_type="session_picker")
    presenter = SimpleNamespace(
        ui=SimpleNamespace(
            _localized_session_type_label=lambda _t, _lang: "Выбор сессии",
        )
    )
    stored = _title_for_storage(
        presenter,
        session,
        "Моя вкладка",
        "ru",
        display_title="Выбор сессии",
    )
    assert stored == "Моя вкладка"


def test_rename_ok_on_localized_default_does_not_rewrite_store():
    session = SimpleNamespace(
        id="s0", session_type="session_picker", title="Session Picker"
    )
    calls: list[tuple[str, str]] = []
    presenter = SimpleNamespace(
        store=SimpleNamespace(settings=SimpleNamespace(current_language="ru")),
        session_manager=SimpleNamespace(
            get_session=lambda _id: session,
            rename_session=lambda session_id, title: calls.append((session_id, title)),
        ),
        main_controller=SimpleNamespace(workspace=SimpleNamespace()),
        ui=SimpleNamespace(
            workspace_tabs=SimpleNamespace(
                tabData=lambda _i: "s0",
                tabText=lambda _i: "Выбор сессии",
            ),
            main_window=object(),
            _localized_session_type_label=lambda _t, _lang: "Выбор сессии",
        ),
    )
    with patch(
        "ui.presenters.main_window.workspace_tab_menu.AppTextInputDialog.get_text",
        return_value=("Выбор сессии", True),
    ):
        handle_workspace_tab_context_action(presenter, 0, "workspace.tab.rename", None)

    assert calls == []
    assert session.title == "Session Picker"
