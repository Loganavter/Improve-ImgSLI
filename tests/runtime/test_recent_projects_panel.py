"""Session Picker recent projects panel smoke tests."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings

from services.io.recent_projects import (
    SORT_NAME,
    VIEW_LIST,
    record_recent_project,
    set_recent_sort_mode,
    set_recent_view_mode,
)
from tabs.session_picker.recent.layout import (
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
    assert panel._sort_button is not None
    assert panel._sort_button.isHidden()

    proj = tmp_path / "demo.imgsli"
    proj.write_text("{}")
    record = record_recent_project(
        proj, session_types=("image_compare",), settings=settings
    )

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
    assert panel._sort_button is not None
    assert not panel._sort_button.isHidden()
    assert panel._items_layout is not None
    assert panel._items_layout.count() == 1

    card = panel._items_layout.itemAt(0).widget()
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
    assert panel._drag_active is True

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
    assert recorded == [str(proj)]

    panel.deleteLater()


def test_recent_panel_header_uses_default_icon_controls(qapp, monkeypatch):
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: [])
    panel = RecentProjectsPanel(tr=_tr)
    assert panel._sort_button is not None
    assert panel._sort_order_button is not None
    assert panel._view_button is not None
    assert panel._sort_button.property("variant") == "default"
    assert panel._sort_order_button.property("variant") == "default"
    assert panel._view_button.property("variant") == "default"
    assert not (panel._view_button._text or "")
    assert not (panel._sort_order_button._text or "")
    chip = panel._header_button_bg()
    assert panel._sort_button._override_bg_color == chip
    assert panel._view_button._override_bg_color == chip
    panel._view_mode = "list"
    panel._sort_order = "asc"
    panel._sync_header_controls()
    assert panel._view_button.toolTip() == "List"
    assert panel._sort_order_button.toolTip() == "Ascending"
    panel.deleteLater()


def test_recent_panel_scroll_disables_viewport_mask(qapp, monkeypatch):
    """Nested OverlayScrollArea must not 1-bit-mask corners over CSD chrome."""
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: [])
    panel = RecentProjectsPanel(tr=_tr)
    assert panel._scroll is not None
    assert panel._scroll._corner_radius == 0
    panel.deleteLater()


def test_grid_columns_for_width_scales_with_space():
    from tabs.session_picker.recent.layout import (
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


def test_recent_panel_scroll_caps_at_two_grid_rows(qapp, tmp_path, monkeypatch):
    from services.io.recent_projects import RecentProjectRecord
    from tabs.session_picker.recent.layout import (
        VISIBLE_ROWS_MAX,
        content_height_for_rows,
        scroll_viewport_height,
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

    # Narrow enough for 3 columns: 7 cards → 3 rows → viewport capped at 2.
    panel = RecentProjectsPanel(tr=_tr)
    panel.resize(560, 800)
    panel.show()
    panel.refresh()
    qapp.processEvents()

    assert panel._scroll is not None
    assert panel._grid_columns == 3
    assert panel._scroll.height() == content_height_for_rows(
        VISIBLE_ROWS_MAX, card_h=GRID_CARD_H
    )
    assert panel._scroll.verticalScrollBar().maximum() > 0

    panel._records = records[:3]  # one grid row at 3 columns
    panel._rebuild_items()
    qapp.processEvents()
    assert panel._scroll.height() == scroll_viewport_height(
        content_rows=1, card_h=GRID_CARD_H
    )
    assert panel._scroll.verticalScrollBar().maximum() == 0

    panel._records = records[:6]  # exactly two grid rows at 3 columns
    panel._rebuild_items()
    qapp.processEvents()
    assert panel._scroll.height() == content_height_for_rows(
        VISIBLE_ROWS_MAX, card_h=GRID_CARD_H
    )
    assert panel._scroll.verticalScrollBar().maximum() == 0
    panel.deleteLater()


def test_recent_panel_grid_uses_available_width(qapp, tmp_path, monkeypatch):
    from services.io.recent_projects import RecentProjectRecord
    from tabs.session_picker.recent.layout import grid_columns_for_width

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
    qapp.processEvents()

    assert panel._scroll is not None
    expected = grid_columns_for_width(panel._grid_content_width())
    assert expected >= 4
    assert panel._grid_columns == expected
    # 8 cards in ≥4 columns → at most 2 rows, no scroll.
    assert panel._scroll.verticalScrollBar().maximum() == 0

    panel.resize(400, 800)
    qapp.processEvents()
    assert panel._grid_columns == grid_columns_for_width(panel._grid_content_width())
    assert panel._grid_columns <= 2
    panel.deleteLater()


def test_recent_panel_resize_preserves_card_widgets(qapp, tmp_path, monkeypatch):
    """Column-count changes must re-slot cards, not recreate them."""
    from services.io.recent_projects import RecentProjectRecord
    from tabs.session_picker.recent.layout import grid_columns_for_width

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
    panel.resize(560, 800)
    panel.show()
    panel.refresh()
    qapp.processEvents()
    assert panel._grid_columns == 3
    before = [
        panel._items_layout.itemAtPosition(*divmod(i, 3)).widget()
        for i in range(6)
    ]
    assert all(w is not None for w in before)

    panel.resize(980, 800)
    qapp.processEvents()
    expected = grid_columns_for_width(panel._grid_content_width())
    assert expected > 3
    assert panel._grid_columns == expected
    cols = panel._grid_columns
    after = [
        panel._items_layout.itemAtPosition(*divmod(i, cols)).widget()
        for i in range(6)
    ]
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
    card = panel._items_layout.itemAt(0).widget()
    assert card.width() == GRID_CARD_W
    assert card.height() == GRID_CARD_H

    panel._view_mode = "list"
    panel._rebuild_items()
    card = panel._items_layout.itemAt(0).widget()
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
    host = panel._items_host
    assert host is not None
    assert len([w for w in host.findChildren(Button) if w.parent() is host]) == 2

    panel._rebuild_items()
    qapp.processEvents()
    live = [w for w in host.findChildren(Button) if w.parent() is host]
    assert len(live) == panel._items_layout.count() == 2
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
    card = panel._items_layout.itemAt(0).widget()
    assert card is not None

    rebuilds = {"n": 0}
    original = panel._rebuild_items

    def _counting_rebuild():
        rebuilds["n"] += 1
        return original()

    panel._rebuild_items = _counting_rebuild  # type: ignore[method-assign]
    panel.on_page_shown()
    assert rebuilds["n"] == 0
    assert panel._items_layout.itemAt(0).widget() is card
    assert panel.updatesEnabled() is True
    panel.deleteLater()


def test_recent_panel_retranslate_keeps_opaque_shelf(qapp, tmp_path, monkeypatch):
    """Language Apply must leave the recent shelf opaque and painted."""
    from PySide6.QtCore import Qt

    from services.io.recent_projects import RecentProjectRecord
    from tabs.session_picker.recent.shelf_chrome import OpaqueFillHost

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
    qapp.processEvents()
    card = panel._items_layout.itemAt(0).widget()
    assert card is not None

    panel._retranslate()
    qapp.processEvents()

    assert panel.updatesEnabled() is True
    assert panel.isVisible() is True
    assert panel._items_layout.count() == 1
    assert panel._items_layout.itemAt(0).widget() is card
    assert panel._scroll.isVisible() is True
    assert panel.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground) is False
    host = panel._items_host
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
    from tabs.session_picker.recent.layout import grid_columns_for_width

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
    panel.resize(560, 800)
    panel.show()
    panel.refresh()
    qapp.processEvents()
    assert panel._grid_columns == 3

    panel.resize(980, 800)
    qapp.processEvents()
    assert panel._grid_columns == grid_columns_for_width(panel._grid_content_width())
    assert panel.updatesEnabled() is True
    panel.deleteLater()


def test_recent_panel_defers_initial_layout_until_timer(qapp, tmp_path, monkeypatch):
    from services.io.recent_projects import RecentProjectRecord

    path = tmp_path / "defer.imgsli"
    path.write_text("{}")
    record = RecentProjectRecord(
        path=str(path),
        display_name="defer",
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
    assert panel._items_layout is not None
    assert panel._items_layout.count() == 0

    panel.show()
    assert panel._initial_refresh_scheduled is True
    qapp.processEvents()
    assert panel._layout_ready is True
    assert panel._items_layout.count() == 1
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

    from tabs.session_picker.recent.layout import PANEL_RADIUS
    from tabs.session_picker.recent.shelf_chrome import OpaqueFillHost

    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: [])
    panel = RecentProjectsPanel(tr=_tr)
    host = panel._items_host
    assert host is not None
    assert isinstance(host, OpaqueFillHost)
    # Explicit paint well — not palette autofill (CSD punch-through).
    assert host.autoFillBackground() is False
    assert host.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground) is False
    assert host.testAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent) is False
    assert panel._panel_bg.alpha() == 255
    assert panel.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground) is False
    # Gaps under cards use the page Window color, not the tinted shelf.
    content = panel._chrome.content_bg
    assert content.alpha() == 255
    assert host._fill == content
    # AA corner cover (no binary mask) rounds that fill against the shelf.
    cover = panel._items.corner_cover
    assert cover is not None
    assert cover._radius == PANEL_RADIUS
    assert cover._color == panel._chrome.panel_bg
    assert panel._scroll._corner_radius == 0
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
    assert panel._items_layout is not None
    assert panel._items_layout.count() == 1
    card = panel._items_layout.itemAt(0).widget()
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
    assert panel._items_layout.count() == 1
    panel.deleteLater()


def test_missing_project_error_detection():
    from ui.main_window.project_io import MainWindowProjectIo

    assert MainWindowProjectIo._is_missing_project_error(FileNotFoundError("gone.imgsli"))
    assert not MainWindowProjectIo._is_missing_project_error(ValueError("x"))
