"""S2-8: list mode inside GalleryGridView (recent items_view parity).

One view, builders swap: grid cards (bg/cover/text) vs list rows
(thumb/text/meta). Pool never mixes modes; series/selection/marquee are
mode-agnostic (operate on live cards).
"""

from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.ui.grid_view import VIEW_GRID, VIEW_LIST
from tabs.image_gallery.ui.list_card import (
    _artifacts_text,
    _badges_text,
    _vlm_text,
    LIST_CARD_H,
)
from tabs.image_gallery.widget import ImageGalleryWidget


def _items(*names: str) -> list[GalleryItem]:
    return [
        GalleryItem(path=Path(f"/gallery/{n}"), mtime_ns=i + 1)
        for i, n in enumerate(names)
    ]


def _grid_ids(card) -> set[str]:
    try:
        return {r.id for r in card._regions}
    except Exception:
        return set()


def test_view_toggle_swaps_builders(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    items = _items("a.png", "b.png")
    w.rebuild_grid(items)
    gv = w._grid_view
    assert gv._view_mode == VIEW_GRID and gv.grid_columns == 4
    assert _grid_ids(gv.card_for(items[0].path)) == {"bg", "cover", "text"}
    w._on_view_toggled(True)
    assert gv._view_mode == VIEW_LIST and gv.grid_columns == 1
    assert _grid_ids(gv.card_for(items[0].path)) == {"thumb", "text", "meta"}
    assert gv.card_for(items[0].path).height() > 0
    w._on_view_toggled(False)
    assert gv._view_mode == VIEW_GRID and gv.grid_columns == 4
    assert _grid_ids(gv.card_for(items[0].path)) == {"bg", "cover", "text"}


def test_pool_never_mixes_modes(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    items = _items("a.png", "b.png")
    w.rebuild_grid(items)
    gv = w._grid_view
    for _ in range(3):
        w._on_view_toggled(True)
        w._on_view_toggled(False)
    modes = set()
    for it in items:
        card = gv.card_for(it.path)
        assert card is not None
        modes.add(getattr(card, "_gallery_view_mode", None))
    assert modes == {VIEW_GRID}
    assert all(
        getattr(c, "_gallery_view_mode", None) == VIEW_GRID for c in gv._pool
    ) or not gv._pool


def test_series_survive_mode_switch(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    items = _items("a.png", "b.png", "c.png")
    w.rebuild_grid(items)
    w._grid_view.set_series([items[:2]], hub_names=["hub1"], collapsed={})
    assert len(w._grid_view._series_headers) == 2  # series + UNGROUPED tail
    w._on_view_toggled(True)
    gv = w._grid_view
    assert gv._series is not None and len(gv._series) == 1
    assert len(gv._series_headers) == 2
    gv._toggle_collapse(0)
    assert gv._collapsed == {0: True}
    # Cluster hidden — tail card still live.
    assert gv.card_for(items[2].path) is not None


def test_selection_and_click_parity_in_list_mode(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    items = _items("a.png", "b.png")
    w.rebuild_grid(items)
    w._on_view_toggled(True)
    w._render_gallery_selection([str(items[0].path)])
    card = w._grid_view.card_for(items[0].path)
    assert getattr(card, "_gallery_sel_applied", (None,))[0] is True
    got: list = []
    orig = w.show_quick_look
    try:
        w.show_quick_look = lambda p: got.append(str(p))  # type: ignore[method-assign]
        w._on_card_toggle(items[1].path, additive=False)
    finally:
        w.show_quick_look = orig  # type: ignore[method-assign]
    assert got == [str(items[1].path)]


def test_list_row_texts() -> None:
    assert _badges_text(_items("a.png")[0]) == ""
    it = _items("a.png")[0]
    it.is_best = True
    it.rank = 3
    assert "★" in _badges_text(it) and "R3" in _badges_text(it)
    rej = _items("b.png")[0]
    rej.rejected = True
    assert "✕" in _badges_text(rej)
    assert _artifacts_text(_items("c.png")[0]) == "…"
    assert _vlm_text(_items("d.png")[0]) == ""
    tie = _items("e.png")[0]
    tie.vlm_tie_pending = True
    assert _vlm_text(tie) == "tie…"


def test_refresh_in_list_mode(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    items = _items("a.png")
    w.rebuild_grid(items)
    w._on_view_toggled(True)
    items[0].rank = 7
    w.refresh_card(items[0])
    card = w._grid_view.card_for(items[0].path)
    assert card is not None
    assert "a.png" in card.toolTip()
    assert LIST_CARD_H == 64
