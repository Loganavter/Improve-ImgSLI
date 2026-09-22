"""Session picker: hook-before-dispose, external delete, scroll-recycle focus.

Regression for task-fix-session-picker-2026-09-20:
- tab stores the page on create_page; dispose/reveal hooks are safe in any order
- soft_refresh rebuilds when a project is deleted or edited externally
- recycling a focused card moves focus to the nearest live card, never index 0
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from services.io.recent_projects import RecentProjectRecord, VIEW_GRID
from tabs.session_picker.recent.use_cases import refresh as refresh_uc


def _record(path: Path, name: str) -> RecentProjectRecord:
    return RecentProjectRecord(
        path=str(path),
        display_name=name,
        opened_at="2026-01-01T00:00:00+00:00",
        session_types=("image_compare",),
    )


# --- hook-before-dispose -------------------------------------------------


def test_tab_stores_widget_and_hooks_are_order_safe(qtbot, monkeypatch):
    import tabs.session_picker.tab as tab_mod
    from tabs.contract import TabContext

    made = []

    class _FakePage:
        def __init__(self, parent, context=None):
            self._parent = parent
            made.append(self)

    monkeypatch.setattr(tab_mod, "SessionPickerWidget", _FakePage)

    from PySide6.QtWidgets import QWidget

    host = QWidget()
    qtbot.addWidget(host)

    tab = tab_mod.SessionPickerTab()
    page = tab.create_page(host, TabContext())
    assert tab._widget is page

    tab.dispose()
    assert tab._widget is None
    tab.dispose()  # double dispose is safe

    fresh = tab_mod.SessionPickerTab()
    fresh.on_host_revealed()  # no page yet — guard hook no-ops
    fresh.dispose()  # dispose before create — safe


# --- external delete / mtime change ---------------------------------------


class _ItemsStub:
    def __init__(self):
        self.applied = 0

    def apply_selection(self):
        self.applied += 1


class _PanelStub:
    def __init__(self):
        self._records: list = []
        self._view_mode = VIEW_GRID
        self._sort_mode = "recent"
        self._sort_order = "desc"
        self._selected_paths: set[str] = set()
        self._layout_ready = False
        self.rebuilds = 0
        self._items = _ItemsStub()

    def _rebuild_items(self):
        self.rebuilds += 1

    def _sync_header_controls(self):
        pass

    def _sync_opaque_fills(self):
        pass


def test_soft_refresh_detects_external_delete_and_mtime(tmp_path: Path, monkeypatch):
    import tabs.session_picker.recent.panel as panel_mod

    proj = tmp_path / "p.imgsli"
    proj.write_text("{}")
    record = _record(proj, "p")

    monkeypatch.setattr(panel_mod, "get_recent_view_mode", lambda **k: VIEW_GRID)
    monkeypatch.setattr(panel_mod, "get_recent_sort_mode", lambda **k: "recent")
    monkeypatch.setattr(panel_mod, "get_recent_sort_order", lambda **k: "desc")
    monkeypatch.setattr(panel_mod, "list_recent_projects", lambda **k: [record])
    monkeypatch.setattr(panel_mod, "sort_recent_projects", lambda recs, **k: list(recs))

    panel = _PanelStub()
    refresh_uc.soft_refresh(panel)
    assert panel.rebuilds == 1
    refresh_uc.soft_refresh(panel)
    assert panel.rebuilds == 1  # stable — no rebuild

    proj.unlink()  # deleted in another app / file manager
    refresh_uc.soft_refresh(panel)
    assert panel.rebuilds == 2

    proj.write_text("{}")  # recreated; mtime differs from the delete snapshot
    refresh_uc.soft_refresh(panel)
    assert panel.rebuilds == 3


# --- scroll-recycle keyboard focus ----------------------------------------


def _tr(key: str, default: str = "", *args, **kwargs) -> str:
    return default or key


def _gallery_records(tmp_path: Path, n: int) -> list[RecentProjectRecord]:
    out = []
    for i in range(n):
        p = tmp_path / f"r{i}.imgsli"
        p.write_text("{}")
        out.append(_record(p, f"r{i}"))
    return out


def test_recycle_moves_focus_to_nearest_live_card(qtbot, tmp_path: Path):
    from PySide6.QtWidgets import QWidget

    from tabs.session_picker.recent.items_view import RecentItemsView

    records = _gallery_records(tmp_path, 12)
    view = RecentItemsView()
    qtbot.addWidget(view)
    view.configure(
        translate=_tr,
        context=None,
        on_activate=lambda *a: None,
        on_context_menu=lambda r: None,
        content_width_provider=lambda: 900,
    )
    owner = QWidget()
    qtbot.addWidget(owner)
    view.show()
    QTest.qWait(30)

    # Materialize every row, then focus the middle card (index 5).
    view._compute_window = lambda: (0, 5)  # type: ignore[method-assign]
    view.sync(records=records, view_mode=VIEW_GRID, updates_owner=owner)
    view._grid_columns = 2
    view._refresh_visible_window(force=True)
    card5 = view.card_for(records[5].path)
    assert card5 is not None
    card5.setFocus(Qt.FocusReason.OtherFocusReason)
    QTest.qWait(20)

    # Scroll far down: rows 0-2 (incl. the focused card) recycle away.
    view._compute_window = lambda: (3, 3)  # type: ignore[method-assign]
    view._refresh_visible_window(force=True)
    QTest.qWait(20)

    from PySide6.QtWidgets import QApplication

    focused = QApplication.focusWidget()
    live_paths = {records[6].path, records[7].path}
    assert focused is not None
    focused_path = next(
        (p for p, c in view._cards_by_path.items() if c is focused), None
    )
    assert focused_path in live_paths  # nearest live row — not index 0
    assert view.card_for(records[0].path) is None  # row 0 stayed recycled
