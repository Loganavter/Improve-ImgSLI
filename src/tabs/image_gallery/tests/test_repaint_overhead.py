"""Gallery repaint overhead guards (loading-cycle stutter).

Regression for the O(N²) cascade: every ``rebuild_grid`` ran a per-item
``refresh_card`` loop, each re-sweeping ``apply_selection`` over the whole
grid (N updates + N sweeps + N² tint repaints per rebuild), and every sweep
repainted every card even when selection was unchanged (thumbnail ticks
re-sweep constantly during load).

Pinned here:
- a grouped rebuild performs exactly ONE selection sweep;
- a repeat sweep with unchanged selection paints zero cards;
- a cold sweep (no stamps yet) paints zero cards when nothing is selected
  (unstamped cards are already visually unselected — stamping without
  painting kills the ~26ms drag-start stall);
- pool-recycled cards still get fresh tooltips (the refresh loop that used
  to do this is gone — tooltips moved to the batch path).
"""

from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.widget import ImageGalleryWidget


def _items(*names: str) -> list[GalleryItem]:
    return [GalleryItem(path=Path(f"/gallery/{n}"), mtime_ns=i) for i, n in enumerate(names)]


def _shown_widget(qtbot, items: list[GalleryItem]) -> ImageGalleryWidget:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()
    qtbot.waitExposed(w)
    w.rebuild_grid(items)
    return w


def test_grouped_rebuild_sweeps_selection_once(qtbot) -> None:
    items = _items("a.png", "b.png", "c.png", "d.png")
    w = _shown_widget(qtbot, items)
    w.set_triage([[items[0], items[1]], [items[2], items[3]]], "camera", None)
    sweeps: list = []
    orig = w._grid_view.apply_selection
    try:
        w._grid_view.apply_selection = lambda *a, **k: (sweeps.append(1), orig(*a, **k))  # type: ignore[method-assign]
        w.rebuild_grid(items)
    finally:
        w._grid_view.apply_selection = orig  # type: ignore[method-assign]
    # Flat pass paints without sweep; restore's set_series sweeps once.
    assert len(sweeps) == 1


def test_repeat_sweep_paints_nothing(qtbot, monkeypatch) -> None:
    from tabs.image_gallery.ui import grid_view as gv_mod

    items = _items("a.png", "b.png", "c.png")
    w = _shown_widget(qtbot, items)
    paints: list = []
    orig = gv_mod.apply_gallery_selection
    try:
        monkeypatch.setattr(
            gv_mod, "apply_gallery_selection",
            lambda card, selected, accent=None: paints.append((card, selected)),
        )
        for card in w._grid_view._cards_by_path.values():
            try:
                delattr(card, "_gallery_sel_applied")
            except Exception:
                pass
        w._grid_view.apply_selection(set())
        first = len(paints)
        assert first == 0  # cold sweep: nothing selected, nothing painted
        w._grid_view.apply_selection(set())
        assert len(paints) == first
        # Changed selection repaints only the toggled card.
        w._grid_view.apply_selection({items[0].path})
        assert len(paints) == first + 1
    finally:
        monkeypatch.setattr(gv_mod, "apply_gallery_selection", orig)


def test_recycled_card_gets_fresh_tooltip(qtbot) -> None:
    w = _shown_widget(qtbot, _items("x.png"))
    card_x = w._grid_view.card_for(Path("/gallery/x.png"))
    assert card_x is not None
    # Pool of 1: rebuilding with a different pool recycles x's card for y.
    w.rebuild_grid(_items("y.png"))
    card_y = w._grid_view.card_for(Path("/gallery/y.png"))
    assert card_y is card_x
    assert "y.png" in str(card_y.toolTip())
    assert "x.png" not in str(card_y.toolTip())
