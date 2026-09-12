"""Workspace session switching via keyboard (Ctrl+Tab / Ctrl+Shift+Tab).

Covers the catalog + keymap entries for ``workspace.next_tab`` /
``workspace.prev_tab``, the pure cycling helper, and the controller runner
that maps the action onto ``switch_workspace_session``.
"""

from __future__ import annotations

from types import SimpleNamespace

from plugins.settings.pages.keyboard import _collect_defaults
from ui.actions.keymap import normalize_sequence
from ui.actions.platform import register_platform_actions
from ui.actions.registry import ActionRegistry
from ui.main_window.menu_controller import MainWindowMenuController
from ui.main_window.use_cases.platform_actions import cycle_session_id


def _noop(*_args, **_kwargs):
    return None


class _Session:
    def __init__(self, session_id: str) -> None:
        self.id = session_id


def test_keymap_defaults_include_workspace_next_prev():
    defaults = {e.action_id: e for e in _collect_defaults().all_entries()}
    assert defaults["workspace.next_tab"].default_shortcut == "Ctrl+Tab"
    assert defaults["workspace.prev_tab"].default_shortcut == "Ctrl+Shift+Tab"
    assert defaults["workspace.next_tab"].owner_tab is None


def test_platform_actions_register_next_prev():
    registry = ActionRegistry()
    runs: list[str] = []
    register_platform_actions(
        show_settings=_noop,
        show_help=_noop,
        new_session=_noop,
        show_find_action=_noop,
        quit_app=_noop,
        open_session_picker=_noop,
        next_session=lambda: runs.append("next"),
        prev_session=lambda: runs.append("prev"),
        registry=registry,
    )
    nxt = registry.get("workspace.next_tab")
    prev = registry.get("workspace.prev_tab")
    assert nxt is not None and prev is not None
    assert normalize_sequence(nxt.shortcut) == "Ctrl+Tab"
    assert normalize_sequence(prev.shortcut) == "Ctrl+Shift+Tab"
    assert nxt.run is not None and prev.run is not None
    nxt.run()
    prev.run()
    assert runs == ["next", "prev"]


def test_cycle_session_id_forward_back_wrap():
    sessions = [_Session("a"), _Session("b"), _Session("c")]
    assert cycle_session_id(sessions, "a", 1) == "b"
    assert cycle_session_id(sessions, "b", 1) == "c"
    assert cycle_session_id(sessions, "c", 1) == "a"
    assert cycle_session_id(sessions, "c", -1) == "b"
    assert cycle_session_id(sessions, "a", -1) == "c"
    assert cycle_session_id(sessions, "missing", 1) == "b"
    assert cycle_session_id(sessions, None, 1) == "b"
    assert cycle_session_id([], "a", 1) is None


def test_controller_switch_workspace_session_cycles():
    sessions = [_Session("a"), _Session("b"), _Session("c")]
    calls: list[str] = []
    workspace = SimpleNamespace(
        switch_workspace_session=lambda session_id: calls.append(session_id)
    )
    manager = SimpleNamespace(
        list_sessions=lambda: list(sessions),
        get_active_session=lambda: sessions[0],
    )
    presenter = SimpleNamespace(session_manager=manager, main_controller=SimpleNamespace(workspace=workspace))
    controller = object.__new__(MainWindowMenuController)
    controller._window = SimpleNamespace(presenter=presenter)

    controller._switch_workspace_session(1)
    assert calls == ["b"]
    calls.clear()
    controller._switch_workspace_session(-1)
    assert calls == ["c"]


def test_controller_switch_noop_when_single_session():
    sessions = [_Session("only")]
    calls: list[str] = []
    workspace = SimpleNamespace(
        switch_workspace_session=lambda session_id: calls.append(session_id)
    )
    manager = SimpleNamespace(
        list_sessions=lambda: list(sessions),
        get_active_session=lambda: sessions[0],
    )
    presenter = SimpleNamespace(session_manager=manager, main_controller=SimpleNamespace(workspace=workspace))
    controller = object.__new__(MainWindowMenuController)
    controller._window = SimpleNamespace(presenter=presenter)

    controller._switch_workspace_session(1)
    assert calls == []
