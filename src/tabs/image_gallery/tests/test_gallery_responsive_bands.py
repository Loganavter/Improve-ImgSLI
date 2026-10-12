"""Responsive gallery grid: wide viewports fill the right half.

 wide window  -> columns grow past GRID_COLUMNS (4);
 2+ sections + wide -> first section left, rest right, draggable
 center separator between them; narrow windows keep the stacked 4-col
 layout (parity with all pre-existing tests).
"""

from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.ui.grid_view import GRID_COLUMNS
from tabs.image_gallery.widget import ImageGalleryWidget


def _items(n: int, prefix: str = "img") -> list[GalleryItem]:
    return [
        GalleryItem(path=Path(f"/gallery/{prefix}-{i:02d}.png"), mtime_ns=i + 1)
        for i in range(n)
    ]


def _pos(gv, widget):
    idx = gv.items_layout.indexOf(widget)
    assert idx >= 0
    r, c, rs, cs = gv.items_layout.getItemPosition(idx)
    return int(r), int(c), int(rs), int(cs)


def test_hidden_view_keeps_four_columns(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.rebuild_grid(_items(3))
    assert w._grid_view.grid_columns == GRID_COLUMNS == 4


def test_wide_viewport_grows_columns(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1900, 900)
    w.show()
    w.rebuild_grid(_items(3))
    qtbot.wait(400)  # let the 150ms adapt timer reflow after show+resize
    gv = w._grid_view
    assert gv.grid_columns > GRID_COLUMNS
    # 3 items fit one wide row (below the UNGROUPED header) — nothing wraps
    # to the "empty right half".
    rows = set()
    for it in w._items:
        card = gv.card_for(it.path)
        assert card is not None
        r, _, _, _ = _pos(gv, card)
        rows.add(r)
    assert len(rows) == 1


def test_narrow_two_sections_stack_full_width(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1100, 800)
    w.show()
    items = _items(6)
    w.rebuild_grid(items)
    qtbot.wait(400)
    gv = w._grid_view
    assert gv.grid_columns == GRID_COLUMNS
    gv.set_series([items[:4]], hub_names=["HUB-A"], collapsed={})
    assert gv._band_state is None
    assert len(gv._series_headers) == 2  # SERIES + UNGROUPED tail
    for hdr in gv._series_headers:
        _, c, _, cs = _pos(gv, hdr)
        assert (c, cs) == (0, GRID_COLUMNS)


def test_wide_two_sections_side_by_side(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1900, 900)
    w.show()
    items = _items(27)
    w.rebuild_grid(items)
    qtbot.wait(400)
    gv = w._grid_view
    gv.set_series([items[:25]], hub_names=["HUB-A"], collapsed={})
    st = gv._band_state
    assert st is not None
    left, right, sep_col = st
    assert left >= 2 and right >= 2
    # Left header spans the left band, tail header the right band.
    r0, c0, _, cs0 = _pos(gv, gv._series_headers[0])
    r1, c1, _, cs1 = _pos(gv, gv._series_headers[1])
    assert (c0, cs0) == (0, left)
    assert (c1, cs1) == (sep_col + 1, right)
    assert r0 == r1 == 0  # headers share the first row, series sit side by side
    # Cards live in their own band.
    card_l = gv.card_for(items[0].path)
    _, cc_l, _, _ = _pos(gv, card_l)
    assert cc_l < sep_col
    card_r = gv.card_for(items[25].path)
    _, cc_r, _, _ = _pos(gv, card_r)
    assert cc_r > sep_col
    # Separator handle is placed and visible.
    sep = gv._band_separator
    assert sep is not None and sep.isVisibleTo(gv.items_host)


def test_set_split_left_redistributes_bands(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1900, 900)
    w.show()
    items = _items(10)
    w.rebuild_grid(items)
    qtbot.wait(400)
    gv = w._grid_view
    gv.set_series([items[:8]], hub_names=["HUB-A"], collapsed={})
    assert gv._band_state is not None
    left, _, _ = gv._band_state
    assert left > 2  # room to shrink the left band
    gv.set_split_left(left - 1)
    st = gv._band_state
    assert st is not None and st[0] == left - 1
    _, c0, _, cs0 = _pos(gv, gv._series_headers[0])
    assert (c0, cs0) == (0, left - 1)


def test_nudge_split_by_px_steps_one_column(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1900, 900)
    w.show()
    items = _items(10)
    w.rebuild_grid(items)
    qtbot.wait(400)
    gv = w._grid_view
    gv.set_series([items[:8]], hub_names=["HUB-A"], collapsed={})
    assert gv._band_state is not None
    left = gv._band_state[0]
    assert left > 2
    stride = gv._grid_stride_px()
    assert stride > 0
    assert gv._nudge_split_by_px(-stride) is True
    assert gv._band_state is not None and gv._band_state[0] == left - 1
    # Tiny jitter below half a stride is a no-op (no replan storm).
    assert gv._nudge_split_by_px(1) is False
    assert gv._band_state is not None and gv._band_state[0] == left - 1


def test_list_mode_stays_single_column_when_wide(qtbot) -> None:
    """List mode never bands: one stretched column even on a wide window."""
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1900, 900)
    w.show()
    items = _items(6)
    w.rebuild_grid(items)
    qtbot.wait(400)
    w._on_view_toggled(True)
    gv = w._grid_view
    assert gv.grid_columns == 1
    gv.set_series([items[:4]], hub_names=["HUB-A"], collapsed={})
    assert gv._band_state is None
    for it in items:
        card = gv.card_for(it.path)
        assert card is not None
        _, c, _, cs = _pos(gv, card)
        assert (c, cs) == (0, 1)


def test_banded_grid_to_list_resets_trailing_columns(qtbot) -> None:
    """A wide banded grid (6 cols) must not leak column minimums into list.

    Regression: ``_sync_series_column_widths`` reset only
    ``max(GRID_COLUMNS, cols)`` columns, so columns 4/5 pinned to the card
    width by the banded grid stayed pinned after a grid->list switch — the
    stretched list column lost ~2 card widths and a dead strip stayed on the
    right (the invisible center splitter's column was among the leaked ones).
    """
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1900, 900)
    w.show()
    items = _items(27)
    w.rebuild_grid(items)
    qtbot.wait(400)
    gv = w._grid_view
    gv.set_series([items[:25]], hub_names=["HUB-A"], collapsed={})
    assert gv._band_state is not None
    assert gv.grid_columns > GRID_COLUMNS

    w._on_view_toggled(True)  # grid -> list
    host_w = gv.items_host.width()
    card = next(iter(gv._cards_by_path.values()))
    assert card.width() >= host_w - 8, (
        f"list row width {card.width()} < host {host_w} — leftover column "
        "minimums from the banded grid"
    )
    for c in range(gv.items_layout.columnCount()):
        assert gv.items_layout.columnMinimumWidth(c) == 0


def test_narrow_resize_returns_to_stacked(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1900, 900)
    w.show()
    items = _items(10)
    w.rebuild_grid(items)
    qtbot.wait(400)
    gv = w._grid_view
    gv.set_series([items[:8]], hub_names=["HUB-A"], collapsed={})
    assert gv._band_state is not None
    w.resize(1100, 800)
    qtbot.wait(400)
    assert gv.grid_columns == GRID_COLUMNS
    assert gv._band_state is None
