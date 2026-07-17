"""Workspace tab context menu includes rename and wires it to SessionManager."""

from types import SimpleNamespace
from unittest.mock import patch

from sli_ui_toolkit.widgets import ContextMenuAction
from ui.presenters.main_window.workspace_tab_menu import (
    build_workspace_tab_context_menu_entries,
    handle_workspace_tab_context_action,
)


def _presenter(*, session_type: str = "image_compare", session_count: int = 1):
    sessions = [
        SimpleNamespace(id=f"s{i}", session_type=session_type, title=f"Tab {i}")
        for i in range(session_count)
    ]
    session_by_id = {s.id: s for s in sessions}

    return SimpleNamespace(
        store=SimpleNamespace(settings=SimpleNamespace(current_language="en")),
        session_manager=SimpleNamespace(
            get_session=lambda session_id: session_by_id.get(session_id),
            list_sessions=lambda: list(sessions),
            rename_session=lambda session_id, title: setattr(
                session_by_id[session_id], "title", title
            )
            or True,
        ),
        main_controller=SimpleNamespace(workspace=SimpleNamespace()),
        ui=SimpleNamespace(
            workspace_tabs=SimpleNamespace(
                tabData=lambda _index: "s0",
                tabText=lambda _index: "Tab 0",
            ),
            main_window=object(),
        ),
    )


def test_workspace_tab_menu_includes_rename():
    entries = build_workspace_tab_context_menu_entries(_presenter(), 0)
    action_ids = [
        entry.action_id for entry in entries if isinstance(entry, ContextMenuAction)
    ]
    assert "workspace.tab.rename" in action_ids
    assert action_ids.index("workspace.tab.rename") == action_ids.index(
        "workspace.tab.close"
    ) + 1


def test_workspace_tab_rename_action_updates_session_title():
    presenter = _presenter()
    with patch(
        "ui.presenters.main_window.workspace_tab_menu.AppTextInputDialog.get_text",
        return_value=("My Tab", True),
    ):
        handle_workspace_tab_context_action(
            presenter, 0, "workspace.tab.rename", None
        )

    assert presenter.session_manager.get_session("s0").title == "My Tab"


def test_workspace_tab_rename_prefills_localized_tab_text():
    presenter = _presenter()
    presenter.ui.workspace_tabs = SimpleNamespace(
        tabData=lambda _index: "s0",
        tabText=lambda _index: "Сравнение изображений",
    )
    captured: list[str] = []

    def _fake_get_text(_parent, _title, _prompt, text="", **_kwargs):
        captured.append(text)
        return text, False

    with patch(
        "ui.presenters.main_window.workspace_tab_menu.AppTextInputDialog.get_text",
        side_effect=_fake_get_text,
    ):
        handle_workspace_tab_context_action(
            presenter, 0, "workspace.tab.rename", None
        )

    assert captured == ["Сравнение изображений"]
