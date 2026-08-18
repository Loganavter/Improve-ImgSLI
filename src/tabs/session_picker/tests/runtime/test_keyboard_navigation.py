"""Keyboard navigation in the session picker (Phase 3 of the keyboard plan).

Covers arrow-key focus movement across the create-session cards and the
recent-projects shelf, plus Enter activation for both.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from services.io.recent_projects import RecentProjectRecord, VIEW_GRID
from tabs.session_picker.recent.panel import RecentProjectsPanel
from tabs.session_picker.widget import SessionPickerWidget

_PANEL = "tabs.session_picker.recent.panel"


def _tr(key: str, default: str = "", *args, **kwargs) -> str:
    return default or key


class _PickerSession:
    def __init__(self) -> None:
        self.id = "picker-session"


class _Context:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self._session = _PickerSession()

    def tr(self, key: str, default: str = "") -> str:
        return default or key

    def call_service(self, name: str, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        if name == "list_session_blueprints":
            return ()
        return None

    def get_active_session(self):
        return self._session


def _records(tmp_path, n: int = 4) -> list[RecentProjectRecord]:
    out: list[RecentProjectRecord] = []
    for i in range(n):
        path = tmp_path / f"kb{i}.imgsli"
        path.write_text("{}")
        out.append(
            RecentProjectRecord(
                path=str(path),
                display_name=f"kb{i}",
                opened_at="2026-01-01T00:00:00+00:00",
                session_types=("image_compare",),
            )
        )
    return out


def _focused_card():
    return QApplication.focusWidget()


def _refresh_recent_panel(panel):
    panel.show()
    panel.refresh()
    QApplication.processEvents()
    panel._items._grid_columns = 2


def test_create_card_arrow_focus_moves_and_wraps(qapp, monkeypatch):
    ctx = _Context()
    widget = SessionPickerWidget(context=ctx)
    widget.show()
    qapp.processEvents()
    entries = widget._card_entries()
    assert len(entries) >= 2

    # No focus yet -> first card.
    assert widget._focus_create_card(1)
    qapp.processEvents()
    assert _focused_card() is entries[0][1]

    widget._focus_create_card(1)
    qapp.processEvents()
    assert _focused_card() is entries[1][1]

    widget._focus_create_card(-1)
    qapp.processEvents()
    assert _focused_card() is entries[0][1]

    # Wrap backward from the first card.
    widget._focus_create_card(-1)
    qapp.processEvents()
    assert _focused_card() is entries[-1][1]
    widget.deleteLater()


def test_create_card_enter_triggers_create(qapp, monkeypatch):
    ctx = _Context()
    widget = SessionPickerWidget(context=ctx)
    widget.show()
    qapp.processEvents()
    entries = widget._card_entries()
    assert entries

    widget._focus_create_card(1)
    qapp.processEvents()
    entries[1][1].click()
    # Create cards use DEFER_CLICK_AWAIT_RIPPLE (~280 ms) before `clicked`.
    QTest.qWait(340)

    replace_calls = [
        c for c in ctx.calls if c[0] == "replace_workspace_session"
    ]
    assert replace_calls
    assert replace_calls[0][1][0] == entries[1][0]
    widget.deleteLater()


def test_recent_arrow_focus_moves_across_live_cards(
    qapp, tmp_path, monkeypatch
):
    records = _records(tmp_path, 4)
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: list(records))
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda recs, **kwargs: list(recs),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: VIEW_GRID)

    panel = RecentProjectsPanel(tr=_tr)
    panel.resize(700, 800)
    _refresh_recent_panel(panel)
    assert panel._items.live_card_count >= 2

    # No focus yet -> first card.
    assert panel._items.navigate_focus(1)
    qapp.processEvents()
    assert _focused_card() is panel._items._cards_by_path.get(records[0].path)

    panel._items.navigate_focus(1)
    qapp.processEvents()
    assert _focused_card() is panel._items._cards_by_path.get(records[1].path)

    panel._items.navigate_focus(-1)
    qapp.processEvents()
    assert _focused_card() is panel._items._cards_by_path.get(records[0].path)
    panel.deleteLater()


def test_recent_enter_activates_focused_card(qapp, tmp_path, monkeypatch):
    records = _records(tmp_path, 3)
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: list(records))
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda recs, **kwargs: list(recs),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: VIEW_GRID)

    opened: list[str] = []
    panel = RecentProjectsPanel(tr=_tr)
    panel.set_open_project_handler(lambda path: opened.append(path))
    panel.resize(700, 800)
    _refresh_recent_panel(panel)

    panel._items.navigate_focus(1)
    qapp.processEvents()
    panel._items.navigate_focus(1)
    qapp.processEvents()
    assert _focused_card() is panel._items._cards_by_path.get(records[1].path)

    panel.keyPressEvent(_KeyEvent(Qt.Key.Key_Return))
    qapp.processEvents()
    assert opened == [records[1].path]
    panel.deleteLater()


class _KeyEvent:
    def __init__(self, key):
        self._key = key
        self.accepted = False

    def key(self):
        return self._key

    def isAutoRepeat(self):
        return False

    def accept(self):
        self.accepted = True
