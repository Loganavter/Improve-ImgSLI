"""Phase 2a — GalleryGridView visible-range signals.

``visible_paths()`` exposes the cards intersecting the viewport (plus a
small vertical overscan) in top-to-bottom display order, and scrollbar
activity emits a debounced ``visible_range_changed``. Wave B (thumbnail
prioritization) consumes this API to decode visible items first instead
of flooding the pool with all N items at ``open_folder`` time.

Geometry comes from layout/card geometry only — never from pixmap data
or arrival order — so these tests use bare ``GalleryItem`` objects with
no thumbnails attached.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.ui.grid_view import GalleryGridView


def _items(n: int, tag: str = "img") -> list[GalleryItem]:
    return [
        GalleryItem(path=Path(f"/gallery/{tag}_{i:03d}.png"), mtime_ns=i)
        for i in range(n)
    ]


def _shown_grid(qtbot, items: list[GalleryItem], width: int = 800, height: int = 400) -> GalleryGridView:
    gv = GalleryGridView()
    qtbot.addWidget(gv)
    gv.resize(width, height)
    gv.show()
    qtbot.waitExposed(gv)
    gv.rebuild_grid(items)
    QApplication.processEvents()
    QApplication.processEvents()
    return gv


def test_empty_grid_returns_no_paths(qtbot) -> None:
    gv = _shown_grid(qtbot, [])
    assert gv.visible_paths() == []


def test_viewport_covering_all_returns_all_in_display_order(qtbot) -> None:
    items = _items(8)
    gv = _shown_grid(qtbot, items, width=1200, height=2000)
    assert gv.visible_paths() == [it.path for it in items]


def test_visible_subset_in_display_order_not_sorted_order(qtbot) -> None:
    # Creation order is deliberately non-alphabetical: display order is
    # the passed list order (row-major layout), not sorted-by-name.
    names = [f"zeta_{i:02d}" for i in range(12)] + [f"alpha_{i:02d}" for i in range(12)]
    items = [GalleryItem(path=Path(f"/gallery/{n}.png"), mtime_ns=i) for i, n in enumerate(names)]
    gv = _shown_grid(qtbot, items, width=800, height=400)

    visible = gv.visible_paths()
    assert 0 < len(visible) < len(items)  # a proper subset: viewport is small
    # Display order: matches the passed list order restricted to visible…
    expected = [it.path for it in items if it.path in set(visible)]
    assert visible == expected
    # …which is NOT alphabetical (creation/sorted order would differ).
    assert [str(p) for p in visible] != sorted(str(p) for p in visible)
    # …and is top-to-bottom geometrically (card y non-decreasing).
    ys = [gv.card_for(p).geometry().y() for p in visible]
    assert ys == sorted(ys)


def test_visible_paths_use_item_path_identity(qtbot) -> None:
    """Returned paths compare == with item.path (controller._find_item)."""
    items = _items(10)
    gv = _shown_grid(qtbot, items, width=1200, height=2000)
    for p in gv.visible_paths():
        assert any(it.path == p for it in items)


def test_scroll_simulation_shows_later_items(qtbot) -> None:
    items = _items(40)
    # Wide enough for all 4 columns (no horizontal clip), short enough
    # to need vertical scrolling.
    gv = _shown_grid(qtbot, items, width=1200, height=400)
    QApplication.processEvents()

    top = gv.visible_paths()
    assert top, "top of grid must show cards"
    assert items[0].path in top
    assert items[-1].path not in top

    vbar = gv.scroll_area.verticalScrollBar()
    vbar.setValue(vbar.maximum())
    QApplication.processEvents()
    QApplication.processEvents()
    bottom = gv.visible_paths()
    assert bottom, "bottom of grid must show cards"
    assert items[-1].path in bottom
    assert items[0].path not in bottom
    # Later-visible items come after earlier ones in display order.
    assert bottom != top


def test_partially_visible_edge_card_counts(qtbot) -> None:
    """Every returned card intersects viewport+overscan; edge cards included."""
    items = _items(40)
    gv = _shown_grid(qtbot, items, width=1200, height=400)
    vbar = gv.scroll_area.verticalScrollBar()
    vbar.setValue(vbar.maximum() // 2)
    QApplication.processEvents()

    visible = gv.visible_paths()
    assert visible
    viewport = gv.scroll_area.viewport()
    vh, vw = viewport.height(), viewport.width()
    overscan = int(vh * gv.VISIBLE_RANGE_OVERSCAN_SCREENS)
    y0 = vbar.value() - overscan
    y1 = vbar.value() + vh + overscan
    for p in visible:
        g = gv.card_for(p).geometry()
        assert g.bottom() >= y0 and g.top() <= y1


def test_debounce_coalesces_rapid_scroll_changes(qtbot) -> None:
    items = _items(40)
    gv = _shown_grid(qtbot, items, width=800, height=400)
    # Let the rebuild-scheduled emit settle, then arm a clean spy.
    qtbot.wait(300)
    gv._visible_debounce.stop()
    gv._last_visible_paths = None
    seen: list[list[Path]] = []
    gv.visible_range_changed.connect(lambda paths: seen.append(list(paths)))

    for _ in range(5):
        gv._schedule_visible_range_emit()
    assert seen == []  # nothing synchronous: recompute is debounced
    qtbot.wait(300)
    assert len(seen) == 1  # rapid schedules coalesced into one emit
    assert seen[0] == gv.visible_paths()


def test_emit_only_on_change(qtbot) -> None:
    items = _items(8)
    gv = _shown_grid(qtbot, items, width=1200, height=2000)
    qtbot.wait(300)
    gv._visible_debounce.stop()
    gv._last_visible_paths = None  # force the next emit to count as a change
    seen: list[list[Path]] = []
    gv.visible_range_changed.connect(lambda paths: seen.append(list(paths)))

    gv._emit_visible_range()
    assert len(seen) == 1
    gv._emit_visible_range()  # same set: no repeat emission
    assert len(seen) == 1
