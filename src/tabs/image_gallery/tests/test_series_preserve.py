"""Series grouping must survive triage refreshes.

Regression: every triage action (reject toggle, keep-best, …) funnels
through ``widget.rebuild_grid`` (flat), which cleared ``grid_view._series``
— SERIES headers vanished on the first reject.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.use_cases import triage as triage_uc
from tabs.image_gallery.widget import ImageGalleryWidget


def _items(*names: str) -> list[GalleryItem]:
    return [GalleryItem(path=Path(f"/gallery/{n}"), mtime_ns=i) for i, n in enumerate(names)]


def _grouped_widget(qtbot, items: list[GalleryItem]) -> ImageGalleryWidget:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()
    w.rebuild_grid(items)
    assert w._grid_view._series == []  # UNGROUPED before triage (never header-less)
    a, b, c, d = items
    w._grid_view.set_series([[a, b], [c, d]], hub_names=["HUB-A", "HUB-C"], collapsed={})
    assert len(w._grid_view._series) == 2
    return w


def _stub_owner(w: ImageGalleryWidget, items: list[GalleryItem]) -> SimpleNamespace:
    return SimpleNamespace(
        state=SimpleNamespace(items=list(items), selected_paths=set(), selected_order=[]),
        widget=w,
    )


def test_toggle_reject_keeps_series(qtbot) -> None:
    """Reject toggle flips the flag but keeps SERIES 1/2 headers."""
    items = _items("a.png", "b.png", "c.png", "d.png")
    w = _grouped_widget(qtbot, items)
    assert triage_uc.toggle_reject(_stub_owner(w, items), items[0].path) is True
    assert bool(items[0].rejected) is True
    assert w._grid_view._series is not None
    assert len(w._grid_view._series) == 2
    assert len(w._grid_view._series_headers) >= 2
    for it in items:
        assert w._grid_view.card_for(it.path) is not None


def test_rebuild_prunes_removed_member_to_ungrouped(qtbot) -> None:
    """Cluster shrinking below 2 drops the header; survivor goes UNGROUPED."""
    items = _items("a.png", "b.png", "c.png", "d.png")
    w = _grouped_widget(qtbot, items)
    w.rebuild_grid(items[:3])  # d.png removed (e.g. via delete X)
    assert w._grid_view._series is not None
    assert len(w._grid_view._series) == 1
    assert [str(m.path) for m in w._grid_view._ungrouped] == [str(items[2].path)]


def test_folder_switch_goes_ungrouped(qtbot) -> None:
    """All-new items (folder switch) show one UNGROUPED section — no stale
    headers from the old pool, and never header-less while triage runs."""
    items = _items("a.png", "b.png", "c.png", "d.png")
    w = _grouped_widget(qtbot, items)
    fresh = _items("x.png", "y.png")
    w.rebuild_grid(fresh)
    assert w._grid_view._series == []
    assert [str(m.path) for m in w._grid_view._ungrouped] == [str(it.path) for it in fresh]
    assert len(w._grid_view._series_headers) == 1  # only the UNGROUPED tail


def test_regroup_reuses_headers_and_cards(qtbot) -> None:
    """Regroup must not demolish widgets: headers retitled, cards kept."""
    items = _items("a.png", "b.png", "c.png", "d.png")
    w = _grouped_widget(qtbot, items)
    headers_before = list(w._grid_view._series_headers)
    cards_before = {str(p): w._grid_view.card_for(p) for p in [it.path for it in items]}
    assert len(headers_before) == 2
    # Absorb c into the first cluster; d falls to UNGROUPED.
    w.set_triage([[items[0], items[1], items[2]]], w._mode, w._source_path)
    headers_after = list(w._grid_view._series_headers)
    assert len(headers_after) == 2  # SERIES + UNGROUPED
    assert headers_after[0] is headers_before[0]
    assert headers_after[1] is headers_before[1]
    for it in items:
        assert w._grid_view.card_for(it.path) is cards_before[str(it.path)]
    assert [str(m.path) for m in w._grid_view._ungrouped] == [str(items[3].path)]


def test_reused_header_collapse_toggles_current_section(qtbot) -> None:
    """Retitled headers toggle their NEW section (closure rebound)."""
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt as _Qt

    items = _items("a.png", "b.png", "c.png", "d.png")
    w = _grouped_widget(qtbot, items)
    # Swap cluster order: header slot 0 now fronts [c, d].
    w.set_triage([[items[2], items[3]], [items[0], items[1]]], w._mode, w._source_path)
    btn = w._grid_view.findChild(object, "GallerySeriesHeaderBtn_0")
    assert btn is not None
    card_c = w._grid_view.card_for(items[2].path)
    card_a = w._grid_view.card_for(items[0].path)
    QTest.mouseClick(btn, _Qt.MouseButton.LeftButton)
    assert w._grid_view._collapsed.get(0) is True
    assert not card_c.isVisible()
    assert card_a.isVisible()
    QTest.mouseClick(btn, _Qt.MouseButton.LeftButton)
    assert w._grid_view._collapsed.get(0) is False
    assert w._grid_view.card_for(items[2].path).isVisible()


def test_dissolved_last_cluster_goes_ungrouped(qtbot) -> None:
    """Deleting a whole group leaves the ex-member under UNGROUPED, not header-less."""
    items = _items("a.png", "b.png", "c.png", "d.png")
    w = _grouped_widget(qtbot, items)
    w.rebuild_grid(items[:1])  # groups [a,b] and [c,d] both dissolved
    assert w._grid_view._series == []
    assert [str(m.path) for m in w._grid_view._ungrouped] == [str(items[0].path)]
    assert len(w._grid_view._series_headers) == 1
    assert w._grid_view.card_for(items[0].path) is not None


def test_dissolve_to_tail_only_goes_ungrouped(qtbot) -> None:
    """Deleting the only cluster keeps never-grouped tail survivors under UNGROUPED."""
    items = _items("a.png", "b.png", "c.png")
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()
    w.rebuild_grid(items)
    w._grid_view.set_series([[items[0], items[1]]], hub_names=["HUB-A"], collapsed={})
    assert [str(m.path) for m in w._grid_view._ungrouped] == [str(items[2].path)]
    w.rebuild_grid(items[2:])
    assert w._grid_view._series == []
    assert [str(m.path) for m in w._grid_view._ungrouped] == [str(items[2].path)]
    assert len(w._grid_view._series_headers) == 1
