"""Session Picker recent projects panel smoke tests."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings

from tests.helpers.drain_until_stable import drain_until_stable

from services.io.recent_projects import (
    SORT_NAME,
    VIEW_LIST,
    record_recent_project,
    set_recent_sort_mode,
    set_recent_view_mode,
)
from ui.widgets.shelf.layout import (
    GRID_CARD_H,
    GRID_CARD_W,
    LIST_CARD_H,
)
from tabs.session_picker.recent.panel import RecentProjectsPanel

_PANEL = "tabs.session_picker.recent.panel"


def _tr(key: str, default: str = "", *args, **kwargs) -> str:
    return default or key


def test_recent_panel_empty_and_populated(qapp, tmp_path, monkeypatch):
    ini = tmp_path / "panel.ini"
    settings = QSettings(str(ini), QSettings.Format.IniFormat)

    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: VIEW_LIST)
    monkeypatch.setattr(f"{_PANEL}.get_recent_sort_mode", lambda **kwargs: SORT_NAME)
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: [])

    panel = RecentProjectsPanel(tr=_tr)
    panel.refresh()
    assert panel._empty_zone is not None
    assert not panel._empty_zone.isHidden()
    assert panel._empty_zone._title == "Load your first project"
    assert panel._header.sort_button is not None
    assert panel._header.sort_button.isHidden()

    proj = tmp_path / "demo.imgsli"
    proj.write_text("{}")
    record = record_recent_project(
        proj, session_types=("image_compare",), settings=settings
    ).record

    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: [record])
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda records, **kwargs: list(records),
    )

    opened: list[str] = []
    panel.set_open_project_handler(lambda path: opened.append(path))
    set_recent_view_mode(VIEW_LIST, settings=settings)
    set_recent_sort_mode(SORT_NAME, settings=settings)
    panel.refresh()
    assert panel._empty_zone.isHidden()
    assert panel._header.sort_button is not None
    assert not panel._header.sort_button.isHidden()
    assert panel._items.live_card_count == 1

    card = panel._items.card_for(record.path)
    assert card is not None
    # Multi-region cards fire ``regionClicked``, not ``clicked``.
    card.regionClicked.emit("text")
    assert opened == [record.path]

    panel.deleteLater()


def test_recent_panel_accepts_project_drop(qapp, tmp_path, monkeypatch):
    from PySide6.QtCore import QMimeData, QPoint, QPointF, QUrl, Qt
    from PySide6.QtGui import QDragEnterEvent, QDropEvent

    recorded: list[str] = []
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: [])
    monkeypatch.setattr(
        f"{_PANEL}.record_recent_project",
        lambda path, **kwargs: recorded.append(str(path)),
    )
    panel = RecentProjectsPanel(tr=_tr)
    opened: list[str] = []
    panel.set_open_project_handler(lambda path: opened.append(path))

    proj = tmp_path / "dropped.imgsli"
    proj.write_text("{}")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(proj))])

    enter = QDragEnterEvent(
        QPoint(10, 10),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    panel.dragEnterEvent(enter)
    assert enter.isAccepted()
    assert panel._drop.drag_active is True

    drop = QDropEvent(
        QPointF(10, 10),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    panel.dropEvent(drop)
    assert drop.isAccepted()
    qapp.processEvents()
    assert opened == []
    # QUrl.toLocalFile may emit forward slashes on Windows; compare as Paths.
    assert len(recorded) == 1
    assert Path(recorded[0]) == proj

    panel.deleteLater()


def test_recent_panel_header_uses_default_icon_controls(qapp, monkeypatch):
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: [])
    panel = RecentProjectsPanel(tr=_tr)
    assert panel._header.sort_button is not None
    assert panel._header.sort_order_button is not None
    assert panel._header.view_button is not None
    assert panel._header.sort_button.property("variant") == "default"
    assert panel._header.sort_order_button.property("variant") == "default"
    assert panel._header.view_button.property("variant") == "default"
    assert not (panel._header.view_button._text or "")
    assert not (panel._header.sort_order_button._text or "")
    chip = panel._header_button_bg()
    assert panel._header.sort_button._override_bg_color == chip
    assert panel._header.view_button._override_bg_color == chip
    panel._view_mode = "list"
    panel._sort_order = "asc"
    panel._sync_header_controls()
    assert panel._header.view_button.toolTip() == "List"
    assert panel._header.sort_order_button.toolTip() == "Ascending"
    panel.deleteLater()


def test_recent_panel_scroll_disables_viewport_mask(qapp, monkeypatch):
    """Nested OverlayScrollArea must not 1-bit-mask corners over CSD chrome."""
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: [])
    panel = RecentProjectsPanel(tr=_tr)
    assert panel._items.scroll_area is not None
    assert panel._items.scroll_area._corner_radius == 0
    panel.deleteLater()


def test_grid_columns_for_width_scales_with_space():
    from ui.widgets.shelf.layout import (
        GRID_CARD_W,
        ITEMS_MARGIN,
        ITEMS_MARGIN_RIGHT,
        ITEMS_SPACING,
        grid_columns_for_width,
    )

    def width_for(cols: int) -> int:
        inner = cols * GRID_CARD_W + max(0, cols - 1) * ITEMS_SPACING
        return inner + ITEMS_MARGIN + ITEMS_MARGIN_RIGHT

    assert grid_columns_for_width(0) == 1
    assert grid_columns_for_width(width_for(1)) == 1
    assert grid_columns_for_width(width_for(3)) == 3
    assert grid_columns_for_width(width_for(5)) == 5
    # One pixel short of a 4th card stays at 3.
    assert grid_columns_for_width(width_for(4) - 1) == 3


def test_recent_panel_bare_panel_falls_back_to_two_rows(qapp, tmp_path, monkeypatch):
    """A bare panel with no real page/window context has no available-space
    signal, so the viewport falls back to the fixed two-grid-row cap."""
    from services.io.recent_projects import RecentProjectRecord
    from ui.widgets.shelf.layout import (
        VISIBLE_ROWS_MAX,
        content_height_for_rows,
    )

    def _record(i: int) -> RecentProjectRecord:
        path = tmp_path / f"demo{i}.imgsli"
        path.write_text("{}")
        return RecentProjectRecord(
            path=str(path),
            display_name=f"demo{i}",
            opened_at="2026-01-01T00:00:00+00:00",
            session_types=("image_compare",),
        )

    records = [_record(i) for i in range(7)]
    monkeypatch.setattr(
        f"{_PANEL}.list_recent_projects",
        lambda **kwargs: list(records),
    )
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda recs, **kwargs: list(recs),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: "grid")

    panel = RecentProjectsPanel(tr=_tr)
    panel.resize(592, 800)
    panel.show()
    panel.refresh()
    drain_until_stable(
        qapp,
        lambda: (panel._items.grid_columns, panel._items.scroll_area.height()),
        timeout_ms=1000,
        stable_frames=2,
    )

    assert panel._items.scroll_area is not None
    assert panel._items.grid_columns == 3
    assert panel._recent_viewport_max_height() == 0  # no page context
    assert panel._items.scroll_area.height() == content_height_for_rows(
        VISIBLE_ROWS_MAX, card_h=GRID_CARD_H
    )
    assert panel._items.scroll_area.verticalScrollBar().maximum() > 0

    panel._records = records[:3]  # one grid row at 3 columns
    panel._rebuild_items()
    drain_until_stable(
        qapp,
        lambda: panel._items.scroll_area.height(),
        timeout_ms=1000,
        stable_frames=2,
    )
    assert panel._items.scroll_area.height() == content_height_for_rows(
        1, card_h=GRID_CARD_H
    )
    assert panel._items.scroll_area.verticalScrollBar().maximum() == 0
    panel.deleteLater()


def test_recent_panel_viewport_uses_available_window_space(qapp, tmp_path, monkeypatch):
    """The shelf viewport fits as many grid rows as the window allows below the
    create-cards (not a fixed two), so a tall window shows several rows and the
    scrollbar only appears when rows overflow that space."""
    from services.io.recent_projects import RecentProjectRecord
    from sli_ui_toolkit.widgets import OverlayScrollArea
    from PySide6.QtWidgets import QVBoxLayout, QWidget
    from ui.widgets.shelf.layout import GRID_CARD_H

    def _record(i: int) -> RecentProjectRecord:
        path = tmp_path / f"fit{i}.imgsli"
        path.write_text("{}")
        return RecentProjectRecord(
            path=str(path),
            display_name=f"fit{i}",
            opened_at="2026-01-01T00:00:00+00:00",
            session_types=("image_compare",),
        )

    monkeypatch.setattr(
        f"{_PANEL}.list_recent_projects",
        lambda **kwargs: [_record(i) for i in range(9)],
    )
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda recs, **kwargs: list(recs),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: "grid")

    win = QWidget()
    win.resize(900, 1080)
    win.show()
    outer = QVBoxLayout(win)
    outer.setContentsMargins(0, 0, 0, 0)
    scroll = OverlayScrollArea(win)
    scroll.set_reserve_scrollbar_space(False)
    outer.addWidget(scroll)
    content = QWidget()
    scroll.setWidget(content)
    lay = QVBoxLayout(content)
    lay.setContentsMargins(48, 40, 48, 40)
    lay.setSpacing(20)
    cards = QWidget()
    cards.setFixedHeight(300)  # stand-in for the create-cards block
    lay.addWidget(cards)
    panel = RecentProjectsPanel(content, tr=_tr)
    lay.addWidget(panel)
    lay.addStretch(1)
    panel.refresh()
    drain_until_stable(
        qapp,
        lambda: (panel._recent_viewport_max_height(), panel._items.scroll_area.height()),
        timeout_ms=1000,
        stable_frames=2,
    )

    max_h = panel._recent_viewport_max_height()
    assert max_h > 0
    # 1080px window leaves room for more than the old fixed two grid rows.
    assert max_h > 2 * (GRID_CARD_H + 12)
    # 9 cards at 4 columns = 3 rows; the grown viewport fits them all.
    assert panel._items.scroll_area.height() > 2 * (GRID_CARD_H + 12)
    assert panel._items.scroll_area.verticalScrollBar().maximum() == 0

    # Many more records overflow the available space -> scrollbar appears.
    panel._records = [_record(i) for i in range(30)]
    panel._rebuild_items()
    drain_until_stable(
        qapp, lambda: panel._items.scroll_area.height(), timeout_ms=1000, stable_frames=2
    )
    assert panel._items.scroll_area.height() == max_h
    assert panel._items.scroll_area.verticalScrollBar().maximum() > 0

    panel.deleteLater()
    win.deleteLater()


def test_recent_panel_grid_uses_available_width(qapp, tmp_path, monkeypatch):
    from services.io.recent_projects import RecentProjectRecord
    from ui.widgets.shelf.layout import grid_columns_for_width

    def _record(i: int) -> RecentProjectRecord:
        path = tmp_path / f"wide{i}.imgsli"
        path.write_text("{}")
        return RecentProjectRecord(
            path=str(path),
            display_name=f"wide{i}",
            opened_at="2026-01-01T00:00:00+00:00",
            session_types=("image_compare",),
        )

    records = [_record(i) for i in range(8)]
    monkeypatch.setattr(
        f"{_PANEL}.list_recent_projects",
        lambda **kwargs: list(records),
    )
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda recs, **kwargs: list(recs),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: "grid")

    panel = RecentProjectsPanel(tr=_tr)
    panel.resize(980, 800)
    panel.show()
    panel.refresh()
    drain_until_stable(
        qapp, lambda: panel._items.grid_columns, timeout_ms=1000, stable_frames=2
    )

    assert panel._items.scroll_area is not None
    expected = grid_columns_for_width(panel._grid_content_width())
    assert expected >= 4
    assert panel._items.grid_columns == expected
    # 8 cards in ≥4 columns → at most 2 rows, no scroll.
    assert panel._items.scroll_area.verticalScrollBar().maximum() == 0

    panel.resize(400, 800)
    drain_until_stable(
        qapp, lambda: panel._items.grid_columns, timeout_ms=1000, stable_frames=2
    )
    assert panel._items.grid_columns == grid_columns_for_width(panel._grid_content_width())
    assert panel._items.grid_columns <= 2
    panel.deleteLater()


def test_recent_panel_grid_shrinks_after_fullscreen_exit(qapp, tmp_path, monkeypatch):
    """Fullscreen→windowed: the restored-size resize can arrive while
    isFullScreen() still reports True. The grid must then use the live panel
    width, not the stale screen-width estimate, or it never shrinks back."""
    from services.io.recent_projects import RecentProjectRecord
    from ui.widgets.shelf.layout import grid_columns_for_width

    def _record(i: int) -> RecentProjectRecord:
        path = tmp_path / f"fs{i}.imgsli"
        path.write_text("{}")
        return RecentProjectRecord(
            path=str(path),
            display_name=f"fs{i}",
            opened_at="2026-01-01T00:00:00+00:00",
            session_types=("image_compare",),
        )

    records = [_record(i) for i in range(8)]
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: list(records))
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda recs, **kwargs: list(recs),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: "grid")

    panel = RecentProjectsPanel(tr=_tr)
    panel.resize(980, 800)
    panel.show()
    panel.refresh()
    drain_until_stable(
        qapp, lambda: panel._items.grid_columns, timeout_ms=1000, stable_frames=2
    )
    wide_columns = panel._items.grid_columns
    assert wide_columns >= 4

    # Transitional frame: geometry already restored to the windowed size, but
    # the fullscreen state flag has not cleared yet.
    monkeypatch.setattr(panel.window(), "isFullScreen", lambda: True)
    panel.resize(400, 800)
    drain_until_stable(
        qapp, lambda: panel._items.grid_columns, timeout_ms=1000, stable_frames=2
    )

    # The panel's live content width (which applies the shelf width floor)
    # drives the column count — not the raw resized width.
    live_columns = grid_columns_for_width(panel._grid_content_width())
    assert panel._items.grid_columns == live_columns
    assert live_columns < wide_columns
    assert panel._items.grid_columns <= 2
    panel.deleteLater()


def test_recent_panel_shelf_height_settles_atomically(qapp, tmp_path, monkeypatch):
    """Column-count changes that flip the shelf 1<->2 rows must settle the panel
    height in the same frame. Without the deferred settle, the scroll grows to
    two rows while the panel is still sized for one row and the shelf jumps one
    part at a time."""
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    from services.io.recent_projects import RecentProjectRecord

    def _record(i: int) -> RecentProjectRecord:
        path = tmp_path / f"settle{i}.imgsli"
        path.write_text("{}")
        return RecentProjectRecord(
            path=str(path),
            display_name=f"settle{i}",
            opened_at="2026-01-01T00:00:00+00:00",
            session_types=("image_compare",),
        )

    records = [_record(i) for i in range(4)]
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: list(records))
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda recs, **kwargs: list(recs),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: "grid")

    window = QWidget()
    lay = QVBoxLayout(window)
    lay.addStretch(1)
    panel = RecentProjectsPanel(window, tr=_tr)
    lay.addWidget(panel)
    window.resize(1000, 800)
    window.show()
    panel.refresh()
    drain_until_stable(
        qapp,
        lambda: (panel._items.scroll_area.height(), panel.height()),
        timeout_ms=1000,
        stable_frames=2,
    )

    one_row_scroll = panel._items.scroll_area.height()
    one_row_panel_h = panel.height()
    assert panel._items.scroll_area.height() <= panel.height()

    def pump():
        # The resize-driven relayout and its height settle run in two nested
        # singleShot timers; wait until geometry stable.
        drain_until_stable(
            qapp,
            lambda: (panel._items.grid_columns, panel._items.scroll_area.height(), panel.height()),
            timeout_ms=1000,
            stable_frames=2,
        )

    # Narrow across the 4->3 column boundary: 4 cards flip to two grid rows.
    window.resize(760, 800)
    pump()
    assert panel._items.grid_columns == 3
    assert panel._items.scroll_area.height() > one_row_scroll
    assert panel._items.scroll_area.height() <= panel.height()  # scroll must fit the panel
    assert panel.height() > one_row_panel_h  # panel grew to fit the taller shelf
    assert panel.updatesEnabled() is True

    # And back up: 3->4 columns flips back to a single row, panel shrinks.
    window.resize(900, 800)
    pump()
    assert panel._items.grid_columns == 4
    assert panel._items.scroll_area.height() == one_row_scroll
    assert panel._items.scroll_area.height() <= panel.height()
    # Panel height is deterministic (header + spacing + scroll + root margins)
    # and returns to the same value after the round-trip — no hysteresis.
    root = panel.layout()
    margins = root.getContentsMargins()
    expected = (
        panel._header.height()
        + root.spacing()
        + panel._items.scroll_area.height()
        + margins[1]
        + margins[3]
    )
    assert abs(panel.height() - expected) <= 2
    assert panel.updatesEnabled() is True

    panel.deleteLater()
    window.deleteLater()


def test_recent_panel_resize_preserves_card_widgets(qapp, tmp_path, monkeypatch):
    """Column-count changes must re-slot cards, not recreate them."""
    from services.io.recent_projects import RecentProjectRecord
    from ui.widgets.shelf.layout import grid_columns_for_width

    def _record(i: int) -> RecentProjectRecord:
        path = tmp_path / f"keep{i}.imgsli"
        path.write_text("{}")
        return RecentProjectRecord(
            path=str(path),
            display_name=f"keep{i}",
            opened_at="2026-01-01T00:00:00+00:00",
            session_types=("image_compare",),
        )

    records = [_record(i) for i in range(6)]
    monkeypatch.setattr(
        f"{_PANEL}.list_recent_projects",
        lambda **kwargs: list(records),
    )
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda recs, **kwargs: list(recs),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: "grid")

    panel = RecentProjectsPanel(tr=_tr)
    panel.resize(592, 800)
    panel.show()
    panel.refresh()
    drain_until_stable(
        qapp, lambda: panel._items.grid_columns, timeout_ms=1000, stable_frames=2
    )
    assert panel._items.grid_columns == 3
    before = [panel._items.card_for(records[i].path) for i in range(6)]
    assert all(w is not None for w in before)

    panel.resize(980, 800)
    drain_until_stable(
        qapp, lambda: panel._items.grid_columns, timeout_ms=1000, stable_frames=2
    )
    expected = grid_columns_for_width(panel._grid_content_width())
    assert expected > 3
    assert panel._items.grid_columns == expected
    after = [panel._items.card_for(records[i].path) for i in range(6)]
    assert after == before
    panel.deleteLater()


def test_recent_panel_cards_use_fixed_size(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QSizePolicy

    from services.io.recent_projects import RecentProjectRecord

    record = RecentProjectRecord(
        path=str(tmp_path / "demo.imgsli"),
        display_name="demo",
        opened_at="2026-01-01T00:00:00+00:00",
        session_types=("image_compare",),
    )
    (tmp_path / "demo.imgsli").write_text("{}")
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: [record])
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda records, **kwargs: list(records),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: "grid")

    panel = RecentProjectsPanel(tr=_tr)
    panel.refresh()
    card = panel._items.card_for(record.path)
    assert card is not None
    assert card.width() == GRID_CARD_W
    assert card.height() == GRID_CARD_H

    panel._view_mode = "list"
    panel._rebuild_items()
    card = panel._items.card_for(record.path)
    assert card is not None
    assert card.height() == LIST_CARD_H
    assert card.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    panel.deleteLater()


def test_recent_panel_clears_orphaned_card_widgets(qapp, tmp_path, monkeypatch):
    """takeAt without reparent left old cards painting under the new grid."""
    from sli_ui_toolkit.widgets import Button

    from services.io.recent_projects import RecentProjectRecord

    def _record(i: int) -> RecentProjectRecord:
        path = tmp_path / f"orphan{i}.imgsli"
        path.write_text("{}")
        return RecentProjectRecord(
            path=str(path),
            display_name=f"orphan{i}",
            opened_at="2026-01-01T00:00:00+00:00",
            session_types=("image_compare",),
        )

    records = [_record(0), _record(1)]
    monkeypatch.setattr(
        f"{_PANEL}.list_recent_projects",
        lambda **kwargs: list(records),
    )
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda recs, **kwargs: list(recs),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: "grid")

    panel = RecentProjectsPanel(tr=_tr)
    panel.resize(560, 800)
    panel.refresh()
    host = panel._items.items_host
    assert host is not None
    assert len([w for w in host.findChildren(Button) if w.parent() is host]) == 2

    panel._rebuild_items()
    drain_until_stable(qapp, lambda: len([w for w in host.findChildren(Button) if w.parent() is host]), timeout_ms=1000, stable_frames=2)
    live = [w for w in host.findChildren(Button) if w.parent() is host]
    assert len(live) == panel._items.live_card_count == 2
    panel.deleteLater()


def test_recent_panel_page_shown_soft_refresh_keeps_cards(qapp, tmp_path, monkeypatch):
    from services.io.recent_projects import RecentProjectRecord

    path = tmp_path / "keep.imgsli"
    path.write_text("{}")
    record = RecentProjectRecord(
        path=str(path),
        display_name="keep",
        opened_at="2026-01-01T00:00:00+00:00",
        session_types=("image_compare",),
    )
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: [record])
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda recs, **kwargs: list(recs),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: "grid")

    panel = RecentProjectsPanel(tr=_tr)
    panel._layout_ready = True
    panel.refresh()
    card = panel._items.card_for(record.path)
    assert card is not None

    rebuilds = {"n": 0}
    original = panel._rebuild_items

    def _counting_rebuild():
        rebuilds["n"] += 1
        return original()

    panel._rebuild_items = _counting_rebuild  # type: ignore[method-assign]
    panel.on_page_shown()
    assert rebuilds["n"] == 0
    assert panel._items.card_for(record.path) is card
    assert panel.updatesEnabled() is True
    panel.deleteLater()


def test_recent_panel_retranslate_keeps_opaque_shelf(qapp, tmp_path, monkeypatch):
    """Language Apply must leave the recent shelf opaque and painted."""
    from PySide6.QtCore import Qt

    from services.io.recent_projects import RecentProjectRecord
    from ui.widgets.shelf import OpaqueFillHost

    path = tmp_path / "lang.imgsli"
    path.write_text("{}")
    record = RecentProjectRecord(
        path=str(path),
        display_name="lang",
        opened_at="2026-01-01T00:00:00+00:00",
        session_types=("image_compare",),
    )
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: [record])
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda recs, **kwargs: list(recs),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: "grid")

    panel = RecentProjectsPanel(tr=_tr)
    panel.resize(560, 800)
    panel.show()
    panel.refresh()
    drain_until_stable(qapp, lambda: panel._items.card_for(record.path) is not None, timeout_ms=1000, stable_frames=2)
    card = panel._items.card_for(record.path)
    assert card is not None

    panel._retranslate()
    drain_until_stable(qapp, lambda: panel.isVisible() and panel.updatesEnabled(), timeout_ms=1000, stable_frames=2)

    assert panel.updatesEnabled() is True
    assert panel.isVisible() is True
    assert panel._items.live_card_count == 1
    assert panel._items.card_for(record.path) is card
    assert panel._items.scroll_area.isVisible() is True
    assert panel.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground) is False
    host = panel._items.items_host
    assert isinstance(host, OpaqueFillHost)
    # Explicit paint — not palette autofill (KNOWN_BUGS CSD punch-through).
    assert host.autoFillBackground() is False
    assert host.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground) is False
    assert host.testAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent) is False
    panel.deleteLater()


def test_recent_panel_refresh_preserves_card_identity(qapp, tmp_path, monkeypatch):
    """Same-path refresh must update cards in place, not destroy/rebuild."""
    from services.io.recent_projects import RecentProjectRecord

    path = tmp_path / "alive.imgsli"
    path.write_text("{}")
    record = RecentProjectRecord(
        path=str(path),
        display_name="alive",
        opened_at="2026-01-01T00:00:00+00:00",
        session_types=("image_compare",),
    )
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: [record])
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda recs, **kwargs: list(recs),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: "grid")

    panel = RecentProjectsPanel(tr=_tr)
    panel.refresh()
    first = panel._items.card_for(str(path))
    assert first is not None

    updated = RecentProjectRecord(
        path=str(path),
        display_name="renamed",
        opened_at="2026-02-01T00:00:00+00:00",
        session_types=("image_compare",),
    )
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: [updated])
    panel.refresh()
    second = panel._items.card_for(str(path))
    assert second is first
    assert second._recent_record.display_name == "renamed"
    assert panel.updatesEnabled() is True
    panel.deleteLater()


def test_recent_panel_relayout_never_leaves_updates_disabled(
    qapp, tmp_path, monkeypatch
):
    from services.io.recent_projects import RecentProjectRecord
    from ui.widgets.shelf.layout import grid_columns_for_width

    def _record(i: int) -> RecentProjectRecord:
        path = tmp_path / f"upd{i}.imgsli"
        path.write_text("{}")
        return RecentProjectRecord(
            path=str(path),
            display_name=f"upd{i}",
            opened_at="2026-01-01T00:00:00+00:00",
            session_types=("image_compare",),
        )

    records = [_record(i) for i in range(6)]
    monkeypatch.setattr(
        f"{_PANEL}.list_recent_projects",
        lambda **kwargs: list(records),
    )
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda recs, **kwargs: list(recs),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: "grid")

    panel = RecentProjectsPanel(tr=_tr)
    panel.resize(592, 800)
    panel.show()
    panel.refresh()
    drain_until_stable(qapp, lambda: panel._items.grid_columns, timeout_ms=1000, stable_frames=2)
    assert panel._items.grid_columns == 3

    panel.resize(980, 800)
    drain_until_stable(qapp, lambda: panel._items.grid_columns, timeout_ms=1000, stable_frames=2)
    assert panel._items.grid_columns == grid_columns_for_width(panel._grid_content_width())
    assert panel.updatesEnabled() is True
    panel.deleteLater()


def test_recent_panel_fills_cards_synchronously_on_show(qapp, tmp_path, monkeypatch):
    from services.io.recent_projects import RecentProjectRecord

    path = tmp_path / "sync.imgsli"
    path.write_text("{}")
    record = RecentProjectRecord(
        path=str(path),
        display_name="sync",
        opened_at="2026-01-01T00:00:00+00:00",
        session_types=("image_compare",),
    )
    monkeypatch.setattr(
        f"{_PANEL}.list_recent_projects",
        lambda **kwargs: [record],
    )
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda recs, **kwargs: list(recs),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: "grid")

    panel = RecentProjectsPanel(tr=_tr)
    panel.resize(560, 800)
    assert panel._layout_ready is False
    assert panel._items.live_card_count == 0

    panel.show()
    # No processEvents / singleShot — first show fills the shelf immediately.
    assert panel._layout_ready is True
    assert panel._items.live_card_count == 1
    panel.deleteLater()


def test_recent_missing_list_card_uses_pastel_red(qapp, tmp_path, monkeypatch):
    from services.io.recent_projects import RecentProjectRecord
    from tabs.session_picker.recent.cards import _MISSING_LIST_BG, build_list_card

    missing_path = tmp_path / "gone.imgsli"
    record = RecentProjectRecord(
        path=str(missing_path),
        display_name="gone",
        opened_at="2026-01-01T00:00:00+00:00",
        pinned_at="2025-12-01T00:00:00+00:00",
        session_types=("image_compare",),
    )
    assert not missing_path.exists()
    card = build_list_card(
        record,
        parent=None,
        tr=_tr,
        on_activate=lambda *_: None,
        on_context_menu=lambda *_: None,
    )
    assert card._override_bg_color == _MISSING_LIST_BG
    assert card._override_bg_color.alpha() == 255
    card.deleteLater()


def test_recent_panel_keeps_scroll_host_opaque(qapp, monkeypatch):
    from PySide6.QtCore import Qt

    from ui.widgets.shelf.layout import PANEL_RADIUS
    from ui.widgets.shelf import OpaqueFillHost

    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: [])
    panel = RecentProjectsPanel(tr=_tr)
    host = panel._items.items_host
    assert host is not None
    assert isinstance(host, OpaqueFillHost)
    # Explicit paint well — not palette autofill (CSD punch-through).
    assert host.autoFillBackground() is False
    assert host.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground) is False
    assert host.testAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent) is False
    assert panel.panel_bg().alpha() == 255
    assert panel.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground) is False
    # Gaps under cards use the page Window color, not the tinted shelf.
    content = panel.content_bg()
    assert content.alpha() == 255
    assert host._fill == content
    # AA corner cover (no binary mask) rounds that fill against the shelf.
    cover = panel._items.corner_cover
    assert cover is not None
    assert cover._radius == PANEL_RADIUS
    assert cover._color == panel.panel_bg()
    assert panel._items.scroll_area._corner_radius == 0
    panel.deleteLater()


def test_recent_missing_grid_cover_is_warning(qapp, tmp_path):
    from services.io.recent_projects import RecentProjectRecord
    from tabs.session_picker.recent.cards import _MISSING_COVER_BG, build_grid_card

    record = RecentProjectRecord(
        path=str(tmp_path / "missing.imgsli"),
        display_name="missing",
        opened_at="2026-01-01T00:00:00+00:00",
        pinned_at="2025-12-01T00:00:00+00:00",
        session_types=("image_compare",),
    )
    card = build_grid_card(
        record,
        parent=None,
        tr=_tr,
        on_activate=lambda *_: None,
        on_context_menu=lambda *_: None,
    )
    cover = next(r for r in card.regions() if r.id == "cover")
    assert cover.pixmap is None
    assert cover.override_bg_color == _MISSING_COVER_BG
    assert cover.icon is not None
    card.deleteLater()


def test_recent_activate_refreshes_when_file_vanishes(qapp, tmp_path, monkeypatch):
    from services.io.recent_projects import RecentProjectRecord

    project = tmp_path / "alive.imgsli"
    project.write_text("{}")
    record = RecentProjectRecord(
        path=str(project),
        display_name="alive",
        opened_at="2026-01-01T00:00:00+00:00",
        session_types=("image_compare",),
    )
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: [record])
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda records, **kwargs: list(records),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: "grid")

    panel = RecentProjectsPanel(tr=_tr)
    panel._layout_ready = True
    panel.refresh()
    opened: list[str] = []
    panel.set_open_project_handler(lambda path: opened.append(path))

    project.unlink()
    panel._activate(record, missing=False)
    assert opened == []
    assert panel._items.live_card_count == 1
    card = panel._items.card_for(record.path)
    assert card is not None
    cover = next(r for r in card.regions() if r.id == "cover")
    assert cover.override_bg_color is not None
    panel.deleteLater()


def test_recent_missing_click_does_not_remove(qapp, tmp_path, monkeypatch):
    from services.io.recent_projects import RecentProjectRecord

    record = RecentProjectRecord(
        path=str(tmp_path / "gone.imgsli"),
        display_name="gone",
        opened_at="2026-01-01T00:00:00+00:00",
        session_types=("image_compare",),
    )
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: [record])
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda records, **kwargs: list(records),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: "grid")
    removed: list[str] = []
    monkeypatch.setattr(
        f"{_PANEL}.remove_recent_project",
        lambda path, **kwargs: removed.append(str(path)) or True,
    )

    panel = RecentProjectsPanel(tr=_tr)
    panel._layout_ready = True
    panel.refresh()
    panel._activate(record, missing=True)
    assert removed == []
    assert panel._items.live_card_count == 1
    panel.deleteLater()


def test_visible_row_window_includes_buffer():
    from ui.widgets.shelf.layout import (
        ITEMS_MARGIN_TOP,
        VIRTUAL_ROW_BUFFER,
        row_stride,
        visible_row_window,
    )

    stride = row_stride(52)
    # At scroll 0, viewport tall enough for ~2 rows → first=0, last includes buffer.
    first, last = visible_row_window(
        0,
        ITEMS_MARGIN_TOP + 2 * stride,
        row_stride_px=stride,
        total_rows=20,
        buffer=VIRTUAL_ROW_BUFFER,
    )
    assert first == 0
    assert last == 1 + VIRTUAL_ROW_BUFFER

    # Scrolled down: window shifts and keeps buffer above/below.
    first, last = visible_row_window(
        ITEMS_MARGIN_TOP + 5 * stride,
        2 * stride,
        row_stride_px=stride,
        total_rows=20,
        buffer=1,
    )
    assert first == 4  # 5 - buffer
    assert last == 7  # 5+1 visible-ish + buffer


def test_recent_panel_virtualizes_large_list(qapp, tmp_path, monkeypatch):
    from services.io.recent_projects import RecentProjectRecord, VIEW_LIST

    def _record(i: int) -> RecentProjectRecord:
        path = tmp_path / f"virt{i}.imgsli"
        path.write_text("{}")
        return RecentProjectRecord(
            path=str(path),
            display_name=f"virt{i}",
            opened_at="2026-01-01T00:00:00+00:00",
            session_types=("image_compare",),
        )

    records = [_record(i) for i in range(40)]
    monkeypatch.setattr(
        f"{_PANEL}.list_recent_projects",
        lambda **kwargs: list(records),
    )
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda recs, **kwargs: list(recs),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: VIEW_LIST)

    panel = RecentProjectsPanel(tr=_tr)
    panel.resize(560, 800)
    panel.show()
    panel.refresh()
    drain_until_stable(qapp, lambda: panel._items.live_card_count, timeout_ms=1000, stable_frames=2)

    live = panel._items.live_card_count
    assert live < len(records)
    assert live > 0
    # Top of the list is live; far rows are not.
    assert panel._items.card_for(records[0].path) is not None
    assert panel._items.card_for(records[-1].path) is None

    bar = panel._items.scroll_area.verticalScrollBar()
    assert bar.maximum() > 0
    top_paths = set(panel._items._cards_by_path)
    bar.setValue(bar.maximum())
    drain_until_stable(qapp, lambda: panel._items.live_card_count, timeout_ms=1000, stable_frames=2)
    bottom_paths = set(panel._items._cards_by_path)
    assert bottom_paths != top_paths
    assert panel._items.card_for(records[-1].path) is not None
    assert panel._items.live_card_count < len(records)
    panel.deleteLater()


def test_missing_project_error_detection():
    from ui.main_window.project_io import MainWindowProjectIo

    assert MainWindowProjectIo._is_missing_project_error(FileNotFoundError("gone.imgsli"))
    assert not MainWindowProjectIo._is_missing_project_error(ValueError("x"))


def test_scale_above_1_geometry_stays_consistent():
    """Layout helpers must return real px at any UI scale: the viewport cap
    never drops below one full scaled row, and the row stride matches the
    scaled card height + spacing exactly (no double-scaling)."""
    from sli_ui_toolkit.managers import UiScale

    from ui.widgets.shelf.layout import (
        ITEMS_MARGIN_BOTTOM,
        ITEMS_MARGIN_TOP,
        ITEMS_SPACING,
        content_height_for_rows,
        row_stride,
        scaled_px,
        scroll_viewport_height,
    )

    UiScale.get_instance().set_factor(1.5)
    try:
        one_row = content_height_for_rows(1, card_h=GRID_CARD_H)
        assert one_row == (
            scaled_px(GRID_CARD_H)
            + scaled_px(ITEMS_MARGIN_TOP)
            + scaled_px(ITEMS_MARGIN_BOTTOM)
        )
        # A max_height smaller than one scaled row must not clip the cards:
        # the cap stays at one full scaled row.
        assert scroll_viewport_height(
            content_rows=4, card_h=GRID_CARD_H, max_height=one_row // 2
        ) >= one_row
        # Stride is the scaled card height plus the scaled spacing — the value
        # the live placement uses per row.
        assert row_stride(GRID_CARD_H) == scaled_px(GRID_CARD_H) + scaled_px(
            ITEMS_SPACING
        )
    finally:
        UiScale.get_instance().set_factor(1.0)


def test_scale_above_1_bare_panel_cap_is_scaled(qapp, tmp_path, monkeypatch):
    """A bare panel (no live height signal) at scale > 1.0 falls back to a
    scaled two-row cap, not the unscaled one that clipped cards to a fraction
    of a row."""
    from sli_ui_toolkit.managers import UiScale

    from services.io.recent_projects import RecentProjectRecord
    from ui.widgets.shelf.layout import (
        VISIBLE_ROWS_MAX,
        content_height_for_rows,
        scaled_px,
    )

    def _record(i: int) -> RecentProjectRecord:
        path = tmp_path / f"scaledemo{i}.imgsli"
        path.write_text("{}")
        return RecentProjectRecord(
            path=str(path),
            display_name=f"scaledemo{i}",
            opened_at="2026-01-01T00:00:00+00:00",
            session_types=("image_compare",),
        )

    records = [_record(i) for i in range(7)]
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: list(records))
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda recs, **kwargs: list(recs),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: "grid")

    UiScale.get_instance().set_factor(1.5)
    try:
        panel = RecentProjectsPanel(tr=_tr)
        panel.resize(592, 800)
        panel.show()
        panel.refresh()
        qapp.processEvents()

        expected = content_height_for_rows(VISIBLE_ROWS_MAX, card_h=GRID_CARD_H)
        assert panel._items.scroll_area.height() == expected
        # The old unscaled fallback (300) was shorter than a single scaled row.
        assert panel._items.scroll_area.height() >= scaled_px(GRID_CARD_H)
        panel.deleteLater()
    finally:
        UiScale.get_instance().set_factor(1.0)


def test_scale_above_1_virtualization_keeps_viewport_filled(qapp, tmp_path, monkeypatch):
    """At UI scale > 1.0 the virtualized window must use the real scaled row
    stride: scrolling a long list must never leave visible cards recycled
    (the old double-scaled stride drifted with the scroll offset and could
    blank the whole viewport)."""
    from sli_ui_toolkit.managers import UiScale

    from services.io.recent_projects import RecentProjectRecord
    from ui.widgets.shelf.layout import (
        GRID_CARD_W,
        ITEMS_MARGIN,
        ITEMS_MARGIN_TOP,
        ITEMS_SPACING,
        row_stride,
        scaled_px,
    )

    def _record(i: int) -> RecentProjectRecord:
        path = tmp_path / f"scalelist{i}.imgsli"
        path.write_text("{}")
        return RecentProjectRecord(
            path=str(path),
            display_name=f"scalelist{i}",
            opened_at="2026-01-01T00:00:00+00:00",
            session_types=("image_compare",),
        )

    records = [_record(i) for i in range(120)]
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: list(records))
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda recs, **kwargs: list(recs),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: "grid")

    UiScale.get_instance().set_factor(1.5)
    try:
        panel = RecentProjectsPanel(tr=_tr)
        panel.resize(592, 800)
        panel.show()
        panel.refresh()
        qapp.processEvents()

        items = panel._items
        scroll = panel._items.scroll_area
        bar = scroll.verticalScrollBar()
        assert bar.maximum() > 0
        stride = row_stride(GRID_CARD_H)
        top = scaled_px(ITEMS_MARGIN_TOP)
        card_w = scaled_px(GRID_CARD_W)
        card_h = scaled_px(GRID_CARD_H)
        for frac in (0.0, 0.2, 0.4, 0.6, 0.8, 0.99):
            bar.setValue(int(frac * bar.maximum()))
            qapp.processEvents()
            y0 = bar.value()
            y1 = y0 + scroll.viewport().height()
            # Pure geometry: every record whose card intersects the viewport
            # (computed from the layout constants, independent of the live
            # card pool) must be live — the window must never recycle
            # visible cards or blank the whole viewport while scrolling.
            expected: list[int] = []
            for i in range(len(records)):
                row, col = divmod(i, max(1, items.grid_columns))
                y = top + row * stride
                if y >= y1 or y + card_h <= y0:
                    continue
                expected.append(i)
            assert expected, f"scroll {y0}: viewport is completely blank"
            for i in expected:
                assert items.card_for(records[i].path) is not None, (
                    f"scroll {y0}: visible record {i} ({records[i].path}) "
                    f"has no live card"
                )
        panel.deleteLater()
    finally:
        UiScale.get_instance().set_factor(1.0)



def test_window_will_fill_screen_and_prelayout_width_estimate(qapp):
    """The shelf's pre-layout width estimate must use the screen width when
    the window is going to be maximized (persisted flag) even if the platform
    has not applied the state yet (Wayland applies it after show) — otherwise
    the grid builds for the transitional normal width and reflows on the
    second frame."""
    from types import SimpleNamespace

    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QApplication, QMainWindow

    from tabs.session_picker.geometry import SESSION_PICKER_PAGE_HORIZONTAL_MARGINS
    from tabs.session_picker.recent.use_cases.sizing import window_will_fill_screen as _window_will_fill_screen

    class FakeScreen:
        def availableGeometry(self):
            return QRect(0, 0, 2560, 1440)

    original = QApplication.primaryScreen
    QApplication.primaryScreen = staticmethod(lambda: FakeScreen())
    try:
        win = QMainWindow()
        win.resize(1024, 768)
        win.screen = lambda: FakeScreen()
        win.store = SimpleNamespace(
            settings=SimpleNamespace(window_was_maximized=True)
        )
        assert _window_will_fill_screen(win) is True
        panel = RecentProjectsPanel(win, tr=_tr)
        width = panel._grid_content_width()
        assert width == 2560 - SESSION_PICKER_PAGE_HORIZONTAL_MARGINS - 32
        panel.deleteLater()
        win.deleteLater()

        # Without the flag (plain restored window), the estimate stays on the
        # window's own width — no screen-width guessing for normal windows.
        win2 = QMainWindow()
        win2.resize(1024, 768)
        win2.screen = lambda: FakeScreen()
        win2.store = SimpleNamespace(
            settings=SimpleNamespace(window_was_maximized=False)
        )
        assert _window_will_fill_screen(win2) is False
        panel2 = RecentProjectsPanel(win2, tr=_tr)
        width2 = panel2._grid_content_width()
        assert width2 == 1024 - SESSION_PICKER_PAGE_HORIZONTAL_MARGINS - 32
        panel2.deleteLater()
        win2.deleteLater()
    finally:
        QApplication.primaryScreen = original



@pytest.mark.parametrize("factor", (1.0, 1.5, 2.0))
def test_shelf_geometry_settles_by_first_drain(qapp, tmp_path, monkeypatch, factor):
    """General first-frame invariant: after the first event-loop drain the
    shelf geometry must be final — later drains may not reflow (the
    "second frame" class of bugs: stale first frame, deferred relayout
    landing later). In a short window (no room for even one row) the shelf
    must clamp to one scaled row instead of keeping the two-row fallback."""
    from PySide6.QtWidgets import QMainWindow, QScrollArea
    from sli_ui_toolkit.managers import UiScale

    from services.io.recent_projects import RecentProjectRecord
    from tabs.session_picker.widget import SessionPickerWidget

    def _record(i: int) -> RecentProjectRecord:
        path = tmp_path / f"stability{i}.imgsli"
        path.write_text("{}")
        return RecentProjectRecord(
            path=str(path),
            display_name=f"stability{i}",
            opened_at="2026-01-01T00:00:00+00:00",
            session_types=("image_compare",),
        )

    records = [_record(i) for i in range(6)]
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: list(records))
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda recs, **kwargs: list(recs),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: "grid")

    class _Ctx:
        def tr(self, key: str, default: str = "") -> str:
            return default or key

        def call_service(self, name: str, *args, **kwargs):
            if name == "list_session_blueprints":
                return ()
            if name == "get_tab_icon":
                return None
            raise RuntimeError(name)

        def get_active_session(self):
            return None

    UiScale.get_instance().set_factor(factor)
    try:
        win = QMainWindow()
        host = QScrollArea(win)
        host.setWidgetResizable(True)
        win.setCentralWidget(host)
        page = SessionPickerWidget(parent=host, context=_Ctx())
        host.setWidget(page)
        # Short window: the shelf does not fit even one row; the page scrolls.
        win.resize(1325, 700)
        win.show()
        qapp.processEvents()

        panel = page._recent_panel
        items = panel._items
        from ui.widgets.shelf.layout import (
            content_height_for_rows,
            GRID_CARD_H,
        )

        one_row = content_height_for_rows(1, card_h=GRID_CARD_H)
        snapshot = (
            items.scroll_area.height(),
            panel.height(),
            items.grid_columns,
        )
        assert snapshot[0] == one_row, (
            "out-of-view shelf must clamp to one scaled row, not the two-row fallback"
        )
        for _ in range(4):
            qapp.processEvents()
        after = (
            items.scroll_area.height(),
            panel.height(),
            items.grid_columns,
        )
        assert after == snapshot, (
            f"factor {factor}: shelf reflowed after the first drain "
            f"{snapshot} -> {after} (second-frame class)"
        )
        page.deleteLater()
        win.deleteLater()
    finally:
        UiScale.get_instance().set_factor(1.0)



def test_live_ui_scale_change_resizes_shelf_in_place(qapp, tmp_path, monkeypatch):
    """A live UiScale change (Settings → Interface scale) must re-apply the
    shelf's scale-dependent geometry in place — card fixed sizes, grid
    columns, scroll viewport height, panel height, layout margins/spacing —
    without a rebuild or app restart (regression: the shelf froze at its
    build-time factor until the next launch while the rest of the UI scaled
    live)."""
    from sli_ui_toolkit.managers import UiScale, scaled_px

    from services.io.recent_projects import RecentProjectRecord
    from ui.widgets.shelf.layout import (
        GRID_CARD_H,
        GRID_CARD_W,
        ITEMS_MARGIN,
        ITEMS_MARGIN_BOTTOM,
        ITEMS_MARGIN_RIGHT,
        ITEMS_MARGIN_TOP,
        ITEMS_SPACING,
        VISIBLE_ROWS_MAX,
        content_height_for_rows,
    )

    def _record(i: int) -> RecentProjectRecord:
        path = tmp_path / f"livescale{i}.imgsli"
        path.write_text("{}")
        return RecentProjectRecord(
            path=str(path),
            display_name=f"livescale{i}",
            opened_at="2026-01-01T00:00:00+00:00",
            session_types=("image_compare",),
        )

    records = [_record(i) for i in range(14)]
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: list(records))
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects",
        lambda recs, **kwargs: list(recs),
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: "grid")

    UiScale.get_instance().set_factor(1.0)
    try:
        panel = RecentProjectsPanel(tr=_tr)
        panel.resize(600, 800)
        panel.show()
        panel.refresh()
        qapp.processEvents()
        items = panel._items
        scroll = panel._items.scroll_area

        def _snapshot():
            cards = list(items._cards_by_path.values())
            card0 = cards[0] if cards else None
            return (
                items.grid_columns,
                scroll.height(),
                panel.height(),
                items.items_layout.getContentsMargins(),
                items.items_layout.horizontalSpacing(),
                items.items_layout.verticalSpacing(),
                None
                if card0 is None
                else (
                    card0.minimumWidth(),
                    card0.maximumWidth(),
                    card0.minimumHeight(),
                    card0.maximumHeight(),
                ),
            )

        at_1_0 = _snapshot()

        # Live factor change on the already-built shelf: the new factor's
        # geometry must land in the same pass (no rebuild, no restart).
        UiScale.get_instance().set_factor(1.5)
        qapp.processEvents()

        cards = list(items._cards_by_path.values())
        assert cards
        assert items.grid_columns == items.resolve_grid_columns()
        assert items.grid_columns <= at_1_0[0], (
            "wider cards must not keep the stale (1.0) column count"
        )
        # Card fixed size follows the new factor.
        assert cards[0].minimumWidth() == cards[0].maximumWidth() == scaled_px(GRID_CARD_W)
        assert (
            cards[0].minimumHeight()
            == cards[0].maximumHeight()
            == scaled_px(GRID_CARD_H)
        )
        # Bare panel (no host height signal): two-row scaled fallback.
        assert scroll.height() == content_height_for_rows(
            VISIBLE_ROWS_MAX, card_h=GRID_CARD_H
        )
        # Panel fixed height re-synced to header + spacing + scroll + margins.
        assert panel.height() == (
            panel._header.sizeHint().height()
            + panel.layout().spacing()
            + scroll.height()
            + panel.layout().getContentsMargins()[1]
            + panel.layout().getContentsMargins()[3]
        )
        assert items.items_layout.getContentsMargins() == (
            scaled_px(ITEMS_MARGIN),
            scaled_px(ITEMS_MARGIN_TOP),
            scaled_px(ITEMS_MARGIN_RIGHT),
            scaled_px(ITEMS_MARGIN_BOTTOM),
        )
        assert items.items_layout.horizontalSpacing() == scaled_px(ITEMS_SPACING)
        assert items.items_layout.verticalSpacing() == scaled_px(ITEMS_SPACING)

        # And back: restoring the factor restores the original geometry.
        UiScale.get_instance().set_factor(1.0)
        qapp.processEvents()
        assert _snapshot() == at_1_0

        panel.deleteLater()
    finally:
        UiScale.get_instance().set_factor(1.0)