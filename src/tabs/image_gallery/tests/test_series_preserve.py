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
    assert w._grid_view._series is None  # flat before triage
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


def test_folder_switch_stays_flat(qtbot) -> None:
    """All-new items (folder switch) keep the flat behavior — no stale headers."""
    items = _items("a.png", "b.png", "c.png", "d.png")
    w = _grouped_widget(qtbot, items)
    fresh = _items("x.png", "y.png")
    w.rebuild_grid(fresh)
    assert w._grid_view._series is None
