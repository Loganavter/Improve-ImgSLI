"""Keyboard navigation in the session picker (Phase 3 of the keyboard plan).

Two layers:
- direct unit checks of the navigation helpers, and
- end-to-end checks that push *real* Qt key events through the widget tree
  (focused card → event filters → handlers), because the cards live inside a
  QAbstractScrollArea whose viewport event filter would otherwise swallow
  arrow keys before the page/panel handlers ever run.
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


def _build_page_with_recent(qapp, tmp_path, monkeypatch, n=4):
    """SessionPickerWidget whose recent shelf is populated with ``n`` records."""
    records = _records(tmp_path, n)
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: list(records))
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda recs, **kwargs: list(recs),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: VIEW_GRID)
    widget = SessionPickerWidget(context=_Context())
    widget.show()
    QTest.qWait(60)
    widget._recent_panel._items._grid_columns = 2
    return widget, records


def _open_calls(widget):
    return [
        c for c in widget._context.calls if c[0] == "replace_workspace_session"
    ]


# --- create-cards: real key events --------------------------------------


def test_create_card_arrows_move_focus_via_real_key_events(qapp, monkeypatch):
    from core.navigation import NavigationManager
    from core.navigation_sections import SessionPickerSection

    widget = SessionPickerWidget(context=_Context())
    widget.show()
    QTest.qWait(50)
    entries = widget._card_entries()
    assert len(entries) >= 2

    manager = NavigationManager.get_instance()
    section = SessionPickerSection(widget)
    manager.register(widget, section)
    try:
        entries[0][1].setFocus(Qt.FocusReason.OtherFocusReason)
        QTest.qWait(20)
        QTest.keyClick(entries[0][1], Qt.Key.Key_Down)
        QTest.qWait(20)
        assert QApplication.focusWidget() is entries[1][1]

        QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Up)
        QTest.qWait(20)
        assert QApplication.focusWidget() is entries[0][1]
    finally:
        manager.unregister(section)
        NavigationManager._instance = None
        widget.deleteLater()


def test_create_card_enter_creates_via_real_key_event(qapp, monkeypatch):
    widget = SessionPickerWidget(context=_Context())
    widget.show()
    QTest.qWait(50)
    entries = widget._card_entries()
    assert entries

    # Focus the second card directly
    entries[1][1].setFocus(Qt.FocusReason.OtherFocusReason)
    QTest.qWait(20)
    QTest.keyClick(entries[1][1], Qt.Key.Key_Return)
    # Create cards use DEFER_CLICK_AWAIT_RIPPLE (~280 ms) before `clicked`.
    QTest.qWait(400)

    replace = _open_calls(widget)
    assert replace
    assert replace[0][1][0] == entries[1][0]
    widget.deleteLater()


# --- recent shelf: real key events --------------------------------------


def test_recent_arrows_move_focus_via_real_key_events(
    qapp, tmp_path, monkeypatch
):
    widget, records = _build_page_with_recent(qapp, tmp_path, monkeypatch)
    panel = widget._recent_panel
    first = panel._items._cards_by_path.get(records[0].path)
    second = panel._items._cards_by_path.get(records[1].path)
    assert first is not None and second is not None

    panel._items.navigate_focus(1)
    QTest.qWait(20)
    assert QApplication.focusWidget() is first

    QTest.keyClick(first, Qt.Key.Key_Right)
    QTest.qWait(20)
    assert QApplication.focusWidget() is second
    widget.deleteLater()


def test_recent_enter_opens_focused_card(qapp, tmp_path, monkeypatch):
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
    panel.show()
    panel.refresh()
    QTest.qWait(60)
    panel._items._grid_columns = 2

    panel._items.navigate_focus(1)
    QTest.qWait(20)
    panel._items.navigate_focus(1)
    QTest.qWait(20)
    card = panel._items._cards_by_path.get(records[1].path)
    assert card is not None and QApplication.focusWidget() is card

    QTest.keyClick(card, Qt.Key.Key_Return)
    QTest.qWait(100)
    assert opened == [records[1].path]
    panel.deleteLater()


# --- boundary handoff between create-cards and recent shelf -------------


def test_down_from_last_create_card_focuses_first_header_button(
    qapp, tmp_path, monkeypatch
):
    """Down from last create-card focuses the first header button on the shelf."""
    widget, records = _build_page_with_recent(qapp, tmp_path, monkeypatch)
    entries = widget._card_entries()
    header = widget._recent_panel._header
    first_btn = next(
        b for b in (header.sort_button, header.sort_order_button, header.view_button)
        if b.isVisible()
    )

    entries[-1][1].setFocus(Qt.FocusReason.OtherFocusReason)
    QTest.qWait(20)
    QTest.keyClick(entries[-1][1], Qt.Key.Key_Down)
    QTest.qWait(20)
    assert QApplication.focusWidget() is first_btn
    widget.deleteLater()


def test_up_from_first_recent_item_returns_to_last_create_card(
    qapp, tmp_path, monkeypatch
):
    widget, records = _build_page_with_recent(qapp, tmp_path, monkeypatch)
    entries = widget._card_entries()
    first_recent = widget._recent_panel._items._cards_by_path.get(records[0].path)
    assert first_recent is not None

    widget._recent_panel._items.navigate_focus(1)
    QTest.qWait(20)
    assert QApplication.focusWidget() is first_recent

    QTest.keyClick(first_recent, Qt.Key.Key_Up)
    QTest.qWait(20)
    header = widget._recent_panel._header
    last_visible_btn = next(
        b for b in reversed(
            (header.sort_button, header.sort_order_button, header.view_button)
        )
        if b.isVisible()
    )
    assert QApplication.focusWidget() is last_visible_btn
    widget.deleteLater()


def test_header_arrows_navigate_between_controls(qapp, tmp_path, monkeypatch):
    widget, records = _build_page_with_recent(qapp, tmp_path, monkeypatch)
    header = widget._recent_panel._header
    btns = [
        b for b in (header.sort_button, header.sort_order_button, header.view_button)
        if b.isVisible()
    ]
    assert len(btns) >= 2

    btns[0].setFocus(Qt.FocusReason.OtherFocusReason)
    QTest.qWait(20)
    QTest.keyClick(btns[0], Qt.Key.Key_Right)
    QTest.qWait(20)
    assert QApplication.focusWidget() is btns[1]

    QTest.keyClick(btns[1], Qt.Key.Key_Left)
    QTest.qWait(20)
    assert QApplication.focusWidget() is btns[0]
    widget.deleteLater()


def test_down_from_last_header_enters_recent_items(qapp, tmp_path, monkeypatch):
    widget, records = _build_page_with_recent(qapp, tmp_path, monkeypatch)
    header = widget._recent_panel._header
    btns = [
        b for b in (header.sort_button, header.sort_order_button, header.view_button)
        if b.isVisible()
    ]
    first_recent = widget._recent_panel._items._cards_by_path.get(records[0].path)
    assert first_recent is not None
    assert btns

    btns[-1].setFocus(Qt.FocusReason.OtherFocusReason)
    QTest.qWait(20)
    QTest.keyClick(btns[-1], Qt.Key.Key_Down)
    QTest.qWait(20)
    assert QApplication.focusWidget() is first_recent
    widget.deleteLater()
