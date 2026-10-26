"""Workspace tabs reorder by drag out of the box, and the order sticks.

Default-on wiring (``ui.main_window.ui.enable_workspace_tab_reordering``) plus
the persistence side (``ui.presenters.main_window.workspace_tab_order``): the
strip's ``tabMoved`` order is written back into the workspace session list,
which is the single source of truth for tab order — the same list a project
file saves and restores. Nothing here is behind a setting.

Red-before: on the pre-change tree the strip is not movable
(``isMovable() is False``), ``Store`` has no ``reorder_workspace_sessions`` and
no ``tabMoved`` hook exists, so ``test_move_tab_persists_order_and_keeps_active``
fails with ``AttributeError: 'Store' object has no attribute
'reorder_workspace_sessions'`` and ``test_workspace_strip_is_movable_by_default``
fails with ``assert False is True``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.store import Store
from core.main_controller_parts.sessions import WorkspaceSessionActions
from ui.icon_manager import AppIcon
from ui.main_window.ui import (
    Ui_ImageComparisonApp,
    enable_workspace_tab_reordering,
)
from ui.presenters.main_window.workspace_tab_order import (
    connect_workspace_tab_reordering,
    on_workspace_tab_moved,
)
from ui.widgets.workspace_tab_strip import WorkspaceTabStrip


class _SessionManager:
    """Minimal SessionManager: the reorder path plus what the presenter reads."""

    def __init__(self, store: Store):
        self.store = store

    def list_sessions(self):
        return self.store.list_workspace_sessions()

    def get_active_session(self):
        return self.store.get_active_workspace_session()

    def get_session(self, session_id):
        return self.store.get_workspace_session(session_id)

    def reorder_sessions(self, session_ids) -> bool:
        return self.store.reorder_workspace_sessions(session_ids)

    def switch_to_session(self, session_id) -> bool:
        return self.store.switch_workspace_session(session_id)

    def close_session(self, session_id) -> bool:
        return self.store.close_workspace_session(session_id)


def _strip() -> WorkspaceTabStrip:
    strip = WorkspaceTabStrip(add_icon=AppIcon.ADD, close_icon=AppIcon.CLOSE)
    enable_workspace_tab_reordering(strip)
    return strip


class _Workspace:
    """One window's worth of the tab strip + its persistence wiring."""

    def __init__(self, store: Store, strip: WorkspaceTabStrip | None = None):
        self.store = store
        self.manager = _SessionManager(store)
        controller = SimpleNamespace(
            session_manager=self.manager,
            event_bus=SimpleNamespace(emit=lambda _event: None),
        )
        self.actions = WorkspaceSessionActions(controller)
        self.ui = Ui_ImageComparisonApp()
        self.ui.main_window = SimpleNamespace(store=store)
        self.ui.workspace_tabs = strip if strip is not None else _strip()
        self.presenter = SimpleNamespace(
            ui=self.ui,
            main_controller=SimpleNamespace(workspace=self.actions),
            session_manager=self.manager,
        )
        assert connect_workspace_tab_reordering(self.presenter) is True
        self.sync()

    @property
    def tabs(self) -> WorkspaceTabStrip:
        return self.ui.workspace_tabs

    def sync(self, active_session_id: str | None = None) -> None:
        if active_session_id is None:
            active = self.manager.get_active_session()
            active_session_id = active.id if active is not None else None
        self.ui.sync_workspace_tabs(self.manager.list_sessions(), active_session_id)

    def visible_order(self) -> list[str]:
        return [self.tabs.tabData(index) for index in range(self.tabs.count())]

    def store_order(self) -> list[str]:
        return [session.id for session in self.store.list_workspace_sessions()]


def _store_with_sessions(session_types: list[str]) -> tuple[Store, list[str]]:
    """A real Store whose session picker is replaced by *session_types*."""
    store = Store()
    picker_id = store.get_active_workspace_session().id
    ids: list[str] = []
    for session_type in session_types:
        session = store.create_workspace_session(
            session_type=session_type, activate=False
        )
        ids.append(session.id)
    store.close_workspace_session(picker_id)
    store.switch_workspace_session(ids[0])
    return store, ids


def test_workspace_strip_is_movable_by_default(qapp):
    """The window that builds the strip switches drag-reorder on itself."""
    from PySide6.QtWidgets import QWidget

    ui = Ui_ImageComparisonApp()
    ui._create_static_widgets(QWidget())

    assert ui.workspace_tabs.isMovable() is True


def test_strip_without_setmovable_does_not_raise(qapp):
    """Older pinned toolkit (no ``setMovable``) keeps the click-only strip."""

    class _StubStrip:
        pass

    assert enable_workspace_tab_reordering(_StubStrip()) is False
    assert enable_workspace_tab_reordering(None) is False


def test_connect_reordering_without_tabmoved_is_a_no_op(qapp):
    """No ``tabMoved`` in the toolkit ⇒ nothing to connect, no raise."""

    class _StubUi:
        workspace_tabs = SimpleNamespace(moveTab=lambda _from, _to: None)

    assert connect_workspace_tab_reordering(SimpleNamespace(ui=_StubUi())) is False


def test_move_tab_persists_order_and_keeps_active(qapp):
    """A simulated drag (``moveTab``) persists the visible order."""
    store, ids = _store_with_sessions(["image_compare", "multi_compare", "image_gallery"])
    ws = _Workspace(store)
    assert ws.visible_order() == ids
    assert ws.store_order() == ids

    ws.tabs.moveTab(2, 0)  # drag the last tab to the front

    expected = [ids[2], ids[0], ids[1]]
    assert ws.visible_order() == expected
    # Persisted through the existing session-list mechanism (project files
    # write/read this very list) — no second store.
    assert ws.store_order() == expected
    # The tab that was current is still current, now at its new position.
    assert store.get_active_workspace_session().id == ids[0]
    assert ws.tabs.currentIndex() == 1
    assert ws.tabs.tabData(ws.tabs.currentIndex()) == ids[0]


def test_handler_persists_visible_order_without_a_movable_strip(qapp):
    """The persistence hook reads the strip, not an index pair."""
    store, ids = _store_with_sessions(["image_compare", "multi_compare"])
    ws = _Workspace(store)
    # Front-to-back inversion as if the user had dragged tab 1 before tab 0.
    ws.tabs.moveTab(0, 1)
    on_workspace_tab_moved(ws.presenter, 0, 1)
    assert ws.store_order() == [ids[1], ids[0]]


def test_rebuild_restores_saved_order_and_active_tab(qapp):
    """A rebuilt strip (restart / project load) shows the saved order."""
    store, ids = _store_with_sessions(["image_compare", "multi_compare", "image_gallery"])
    ws = _Workspace(store)
    ws.tabs.moveTab(2, 0)
    saved = [ids[2], ids[0], ids[1]]
    assert ws.store_order() == saved

    # New strip, same store: the order comes from the session list.
    rebuilt = _Workspace(store)

    assert rebuilt.visible_order() == saved
    assert rebuilt.store_order() == saved
    assert rebuilt.tabs.currentIndex() == saved.index(ids[0])
    assert store.get_active_workspace_session().id == ids[0]


def test_restoring_order_is_not_persisted_as_a_drag(qapp):
    """Rebuild-time ``moveTab`` must not write back an intermediate order."""
    store, ids = _store_with_sessions(["image_compare", "multi_compare", "image_gallery"])
    ws = _Workspace(store)
    ws.tabs.moveTab(2, 0)
    saved = ws.store_order()

    writes: list[list[str]] = []
    original = ws.actions.reorder_workspace_sessions
    ws.actions.reorder_workspace_sessions = lambda session_ids: (
        writes.append(list(session_ids)) or original(session_ids)
    )
    ws.sync()

    assert writes == []  # the restore path never reports itself as a drag
    assert ws.store_order() == saved
    assert ws.visible_order() == saved


def test_shrunk_session_set_restores_sanely(qapp):
    """A closed session is simply absent — no index-based shuffle."""
    store, ids = _store_with_sessions(["image_compare", "multi_compare", "image_gallery"])
    ws = _Workspace(store)
    ws.tabs.moveTab(2, 0)
    reordered = [ids[2], ids[0], ids[1]]
    assert ws.store_order() == reordered

    # Close the session that is now in the middle of the visible order.
    store.close_workspace_session(ids[0])

    # A fresh strip over the shrunken session list: unknown ids skipped, the
    # survivors keep their relative order.
    rebuilt = _Workspace(store)
    assert rebuilt.visible_order() == [ids[2], ids[1]]
    assert rebuilt.store_order() == [ids[2], ids[1]]
    # Same happens in place, on the strip that still shows the stale order.
    ws.sync()
    assert ws.visible_order() == [ids[2], ids[1]]


def test_new_session_appends_and_keeps_existing_order(qapp):
    """A session added after the reorder lands last; nothing else moves."""
    store, ids = _store_with_sessions(["image_compare", "multi_compare", "image_gallery"])
    ws = _Workspace(store)
    ws.tabs.moveTab(2, 0)
    saved = [ids[2], ids[0], ids[1]]

    new_session = store.create_workspace_session(
        session_type="image_compare", activate=False
    )
    ws.sync()

    assert ws.visible_order() == saved + [new_session.id]
    assert ws.store_order() == saved + [new_session.id]


def test_ctrl_tab_cycle_follows_visible_order(qapp):
    """Ctrl+Tab walks the session list, which now equals the visible order."""
    from ui.main_window.use_cases.platform_actions import cycle_session_id

    store, ids = _store_with_sessions(["image_compare", "multi_compare", "image_gallery"])
    ws = _Workspace(store)
    ws.tabs.moveTab(2, 0)  # visible: c, a, b

    sessions = list(ws.manager.list_sessions())
    active = ws.manager.get_active_session()
    assert [session.id for session in sessions] == [ids[2], ids[0], ids[1]]
    assert cycle_session_id(sessions, active.id, 1) == ids[1]
    assert cycle_session_id(sessions, active.id, -1) == ids[2]


def test_reorder_ignores_unknown_and_missing_ids():
    """Store-level guard: unknown ids skipped, missing ones kept at the end."""
    store, ids = _store_with_sessions(["image_compare", "multi_compare", "image_gallery"])

    assert store.reorder_workspace_sessions(["gone", ids[1], ids[1]]) is True
    assert [session.id for session in store.list_workspace_sessions()] == [
        ids[1],
        ids[0],
        ids[2],
    ]
    # No-op when the order already matches — listeners are not woken.
    changes: list[str] = []
    store.on_change(changes.append)
    assert store.reorder_workspace_sessions([ids[1], ids[0], ids[2]]) is False
    assert changes == []


@pytest.mark.parametrize("empty", [[], None])
def test_reorder_without_ids_keeps_every_session(empty):
    store, ids = _store_with_sessions(["image_compare", "multi_compare"])
    assert store.reorder_workspace_sessions(empty) is False
    assert [session.id for session in store.list_workspace_sessions()] == ids
