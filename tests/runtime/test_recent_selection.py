"""Recent shelf multi-select (Ctrl+click + in-window marquee)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QMouseEvent

from services.io.recent_projects import RecentProjectRecord, VIEW_GRID, VIEW_LIST
from tabs.session_picker.recent.layout import GRID_CARD_H, GRID_CARD_W, ITEMS_MARGIN
from tabs.session_picker.recent.panel import RecentProjectsPanel
from tabs.session_picker.recent.selection import (
    card_rect_for_index,
    paths_intersecting_rect,
)

_PANEL = "tabs.session_picker.recent.panel"


def _tr(key: str, default: str = "", *args, **kwargs) -> str:
    return default or key


def _records(tmp_path, n: int = 6) -> list[RecentProjectRecord]:
    out: list[RecentProjectRecord] = []
    for i in range(n):
        path = tmp_path / f"sel{i}.imgsli"
        path.write_text("{}")
        out.append(
            RecentProjectRecord(
                path=str(path),
                display_name=f"sel{i}",
                opened_at="2026-01-01T00:00:00+00:00",
                session_types=("image_compare",),
            )
        )
    return out


def test_paths_intersecting_rect_hits_grid_cards(tmp_path):
    records = _records(tmp_path, 4)
    # First card origin
    first = card_rect_for_index(
        0, view_mode=VIEW_GRID, columns=2, host_width=560
    )
    hits = paths_intersecting_rect(
        records,
        first.adjusted(2, 2, -2, -2),
        view_mode=VIEW_GRID,
        columns=2,
        host_width=560,
    )
    assert records[0].path in hits
    assert len(hits) == 1

    # Band covering two columns of first row
    band = QRect(
        ITEMS_MARGIN,
        ITEMS_MARGIN,
        GRID_CARD_W * 2 + 20,
        GRID_CARD_H,
    )
    hits = paths_intersecting_rect(
        records,
        band,
        view_mode=VIEW_GRID,
        columns=2,
        host_width=560,
    )
    assert {records[0].path, records[1].path} <= hits


def test_ctrl_click_toggles_selection_without_open(qapp, tmp_path, monkeypatch):
    records = _records(tmp_path, 3)
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: list(records))
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda recs, **kwargs: list(recs),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: VIEW_LIST)

    opened: list[str] = []
    panel = RecentProjectsPanel(tr=_tr)
    panel.set_open_project_handler(lambda path: opened.append(path))
    panel.resize(560, 800)
    panel.show()
    panel.refresh()
    qapp.processEvents()

    panel._on_card_activate(
        records[0], False, Qt.KeyboardModifier.ControlModifier
    )
    assert records[0].path in panel._selected_paths
    assert opened == []

    panel._on_card_activate(
        records[1], False, Qt.KeyboardModifier.ControlModifier
    )
    assert panel._selected_paths == {records[0].path, records[1].path}

    panel._on_card_activate(
        records[0], False, Qt.KeyboardModifier.ControlModifier
    )
    assert panel._selected_paths == {records[1].path}
    panel.deleteLater()


def test_marquee_preview_updates_live_before_release(qapp, tmp_path, monkeypatch):
    records = _records(tmp_path, 4)
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: list(records))
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda recs, **kwargs: list(recs),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: VIEW_LIST)

    panel = RecentProjectsPanel(tr=_tr)
    panel.refresh()
    # Preview must light cards without committing yet.
    panel._on_marquee_preview({records[0].path, records[1].path}, False)
    assert panel._selected_paths == set()
    card0 = panel._items.card_for(records[0].path)
    assert card0 is not None
    assert card0._override_bg_color is not None
    # Pastel mix — not raw theme accent.
    assert card0._override_bg_color.name() not in ("#0078d4", "#0096ff")
    assert card0.is_bg_locked() is True

    panel._on_marquee_commit({records[0].path, records[1].path}, False)
    assert panel._selected_paths == {records[0].path, records[1].path}
    assert card0.is_bg_locked() is True
    panel.deleteLater()


def test_ctrl_select_locks_bg_immediately(qapp, tmp_path, monkeypatch):
    records = _records(tmp_path, 2)
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: list(records))
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda recs, **kwargs: list(recs),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: VIEW_LIST)

    panel = RecentProjectsPanel(tr=_tr)
    panel.refresh()
    panel._on_card_activate(
        records[0], False, Qt.KeyboardModifier.ControlModifier
    )
    card0 = panel._items.card_for(records[0].path)
    assert card0 is not None
    assert card0._override_bg_color is not None
    assert card0.is_bg_locked() is True

    panel._on_card_activate(
        records[0], False, Qt.KeyboardModifier.ControlModifier
    )
    assert card0.is_bg_locked() is False
    assert card0._override_bg_color is None
    panel.deleteLater()


def test_marquee_commit_replaces_and_additive(qapp, tmp_path, monkeypatch):
    records = _records(tmp_path, 4)
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: list(records))
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda recs, **kwargs: list(recs),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: VIEW_LIST)

    panel = RecentProjectsPanel(tr=_tr)
    panel.refresh()
    panel._on_marquee_commit({records[0].path, records[1].path}, False)
    assert panel._selected_paths == {records[0].path, records[1].path}

    panel._on_marquee_commit({records[2].path}, True)
    assert panel._selected_paths == {
        records[0].path,
        records[1].path,
        records[2].path,
    }

    panel._on_marquee_commit(set(), False)
    assert panel._selected_paths == set()
    panel.deleteLater()


def test_empty_host_press_starts_in_window_marquee(qapp, tmp_path, monkeypatch):
    records = _records(tmp_path, 2)
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: list(records))
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda recs, **kwargs: list(recs),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: VIEW_LIST)

    panel = RecentProjectsPanel(tr=_tr)
    panel.resize(560, 800)
    panel.show()
    panel.refresh()
    qapp.processEvents()

    host = panel._items.items_host
    # Click below cards into empty host space.
    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPoint(20, host.height() - 4),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    assert panel._items.eventFilter(host, press) is True
    gesture = panel._items._marquee_gesture
    assert gesture is not None
    assert gesture.active is True
    assert gesture.app_filter_installed is True
    assert gesture.overlay is not None
    assert gesture.overlay.isVisible()
    assert gesture.overlay.testAttribute(
        Qt.WidgetAttribute.WA_TransparentForMouseEvents
    )

    release = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPoint(200, host.height() - 4),
        host.mapToGlobal(QPoint(200, host.height() - 4)),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    # Drag tracking uses the toolkit gesture app filter (no grabMouse on Wayland).
    assert gesture.eventFilter(panel, release) is True
    assert not gesture.overlay.isVisible()
    assert gesture.app_filter_installed is False
    panel.deleteLater()
