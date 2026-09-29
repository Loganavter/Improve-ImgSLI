"""Recent card context menu: FM-style Sort by / View submenus.

Submenu checkmarks mirror the live persisted prefs; submenu actions
persist + notify so the panel refreshes like a header-chip click.
"""

from __future__ import annotations

from types import SimpleNamespace

from services.io.recent_projects import (
    SORT_ASC,
    SORT_NAME,
    VIEW_LIST,
)
from tabs.session_picker.recent.context_menu import (
    handle_sort_view_action,
    sort_view_menu_entries,
)


def _tr(key: str, default: str, **kwargs) -> str:
    return default


def _submenu(entry_id: str, entries):
    from sli_ui_toolkit.widgets import ContextMenuAction

    for e in entries:
        if isinstance(e, ContextMenuAction) and e.action_id == entry_id:
            return e
    raise AssertionError(f"submenu {entry_id} not found")


def test_submenus_present_with_live_checks() -> None:
    entries = sort_view_menu_entries(_tr)
    sort_menu = _submenu("recent.sort_by", entries)
    by_id = {a.action_id: a for a in sort_menu.children if hasattr(a, "action_id")}
    assert set(by_id) >= {
        "recent.sort.modified", "recent.sort.created", "recent.sort.name",
        "recent.sort.asc", "recent.sort.desc",
    }
    # Exactly one criterion + one direction checked (live prefs).
    crit = [by_id[i].checked for i in ("recent.sort.modified", "recent.sort.created", "recent.sort.name")]
    assert sum(1 for c in crit if c) == 1
    assert (by_id["recent.sort.asc"].checked, by_id["recent.sort.desc"].checked) in (
        (True, False), (False, True),
    )
    view_menu = _submenu("recent.view", entries)
    assert [(a.action_id, a.checked) for a in view_menu.children] == [
        ("recent.view.grid", True), ("recent.view.list", False),
    ] or [(a.action_id, a.checked) for a in view_menu.children] == [
        ("recent.view.grid", False), ("recent.view.list", True),
    ]


def test_submenu_actions_persist_and_notify(monkeypatch) -> None:
    from services.io.recent_projects import (
        get_recent_sort_mode,
        get_recent_sort_order,
        get_recent_view_mode,
    )

    # Save live prefs; restore them at the end (QSettings are real here).
    prev = (get_recent_sort_mode(), get_recent_sort_order(), get_recent_view_mode())
    notified: list = []
    assert handle_sort_view_action("recent.sort.name", SORT_NAME, lambda: notified.append(None)) is True
    assert handle_sort_view_action("recent.sort.asc", SORT_ASC, lambda: notified.append(None)) is True
    assert handle_sort_view_action("recent.view.list", VIEW_LIST, lambda: notified.append(None)) is True
    assert notified == [None, None, None]

    assert get_recent_sort_mode() == SORT_NAME
    assert get_recent_sort_order() == SORT_ASC
    assert get_recent_view_mode() == VIEW_LIST

    # Restore live prefs so other tests (and the dev machine) are unaffected.
    handle_sort_view_action(f"recent.sort.{prev[0]}", prev[0], None)
    handle_sort_view_action(f"recent.sort.{prev[1]}", prev[1], None)
    handle_sort_view_action(f"recent.view.{prev[2]}", prev[2], None)
    assert handle_sort_view_action("recent.open", None, None) is False


def test_record_menu_has_no_sort_view(monkeypatch) -> None:
    """Sort by / View live in the empty-shelf menu (FM background menu),
    never in the per-record menu."""
    import tabs.session_picker.recent.context_menu as _cm
    from services.io.recent_projects import RecentProjectRecord

    captured: dict = {}

    def _fake_open(*, source_widget, global_pos, entries, key, on_triggered=None):
        captured["entries"] = tuple(entries)
        captured["on_triggered"] = on_triggered
        return SimpleNamespace()

    monkeypatch.setattr(_cm, "open_context_menu_entries", _fake_open)
    record = RecentProjectRecord(path="/tmp/x.imgsli", display_name="x", opened_at="")
    _cm.open_recent_project_menu(
        source_widget=SimpleNamespace(),
        record=record,
        translate=_tr,
        on_open=lambda r: None,
        on_remove=lambda r: None,
    )
    from sli_ui_toolkit.widgets import ContextMenuAction

    ids = [e.action_id for e in captured["entries"] if isinstance(e, ContextMenuAction)]
    assert "recent.sort_by" not in ids
    assert "recent.view" not in ids


def test_empty_menu_includes_submenus(monkeypatch) -> None:
    """open_recent_empty_menu shows the submenus and dispatches them."""
    import tabs.session_picker.recent.context_menu as _cm

    captured: dict = {}

    def _fake_open(*, source_widget, global_pos, entries, key, on_triggered=None):
        captured["entries"] = tuple(entries)
        captured["on_triggered"] = on_triggered
        return SimpleNamespace()

    monkeypatch.setattr(_cm, "open_context_menu_entries", _fake_open)
    notified: list = []
    _cm.open_recent_empty_menu(
        source_widget=SimpleNamespace(),
        global_pos=None,
        translate=_tr,
        on_prefs_changed=lambda: notified.append(None),
    )
    from sli_ui_toolkit.widgets import ContextMenuAction

    ids: list[str] = []
    for e in captured["entries"]:
        if isinstance(e, ContextMenuAction):
            ids.append(e.action_id)
            ids.extend(
                a.action_id for a in e.children if isinstance(a, ContextMenuAction)
            )
    assert "recent.sort_by" in ids
    assert "recent.view" in ids
    assert "recent.sort.name" in ids
    assert "recent.view.list" in ids
    captured["on_triggered"]("recent.sort.name", SORT_NAME)
    assert notified == [None]


def test_empty_host_right_press_opens_background_menu(qtbot) -> None:
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    from tabs.session_picker.recent.items_view import RecentItemsView

    view = RecentItemsView()
    qtbot.addWidget(view)
    fired: list = []
    view.configure(
        translate=_tr,
        context=None,
        on_activate=lambda *a: None,
        on_context_menu=lambda r: None,
        content_width_provider=lambda: 900,
        on_empty_context_menu=lambda gp: fired.append(gp),
    )
    view.show()
    qtbot.wait(50)
    host = view.items_host
    empty = QPoint(host.width() - 30, host.height() - 30)
    assert host.childAt(empty) is None
    press = QMouseEvent(
        QEvent.Type.MouseButtonPress, QPointF(empty), QPointF(host.mapToGlobal(empty)),
        Qt.MouseButton.RightButton, Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    assert view.eventFilter(host, press) is True
    assert len(fired) == 1
