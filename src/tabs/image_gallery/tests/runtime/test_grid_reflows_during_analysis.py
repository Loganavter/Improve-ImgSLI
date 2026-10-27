"""The card grid follows a window resize WHILE the folder analysis runs.

Falsification (owner report 2026-10-27, live): with the analysis badges
spinning, a window resize left every card glued to its old place; once the run
finished the resize moved them freely again.

Root cause (not "no reflow call" — a dead resize path): the live analysis
frames are the S1 window opened by ``widget_parts.status.set_scanning``. It
makes the gallery's transparent scanning surface the CURRENT page of the
content ``QStackedWidget`` and only calls ``show()`` on the grid ("keep in
stack but not current"). A stacked layout sizes its current page only, so the
grid kept the rect it had when the page was switched away: no ``resizeEvent``
→ no ``_adapt_timer`` → no ``_compute_columns`` → no reflow, for the whole
run. ``set_triage`` makes the grid current again and the geometry snaps — the
"after the analysis it works again".

These tests drive that exact state through the widget's public surface
(``set_scanning``), so they fail on the pre-fix build:

* ``test_cards_follow_a_resize_while_the_analysis_covers_the_window`` —
  pre-fix the grid never resized (stale width, stale column count, zero moved
  cards).
* ``test_a_resize_replans_the_series_layout_without_restamping_cards`` —
  pre-fix the resize re-stamped every card's content (one
  ``update_gallery_card`` per card) instead of moving geometry.
* ``test_a_resize_does_not_turn_a_chunked_build_into_a_full_build`` — pre-fix
  the resize cancelled the in-flight chunked rebuild and pulled the whole pool
  in synchronously.
"""

from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.widget import ImageGalleryWidget


def _items(n: int, prefix: str = "img") -> list[GalleryItem]:
    return [
        GalleryItem(path=Path(f"/gallery/{prefix}-{i:03d}.png"), mtime_ns=i + 1)
        for i in range(n)
    ]


def _geometry(gv, items) -> dict[str, tuple]:
    return {str(it.path): tuple(gv.card_for(it.path).geometry().getRect()) for it in items}


def _display_order(gv, items) -> list[str]:
    """Path order as laid out (row, then column) — the visible reading order."""
    placed: list[tuple[tuple[int, int], str]] = []
    for it in items:
        card = gv.card_for(it.path)
        idx = gv.items_layout.indexOf(card)
        assert idx >= 0, f"card for {it.path} is not in the layout"
        row, col, _rs, _cs = gv.items_layout.getItemPosition(idx)
        placed.append(((int(row), int(col)), str(it.path)))
    placed.sort()
    return [path for _cell, path in placed]


def test_cards_follow_a_resize_while_the_analysis_covers_the_window(qtbot) -> None:
    """Resize during the run moves the cards; nothing is rebuilt for it."""
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1400, 800)
    w.show()
    items = _items(40)
    w.rebuild_grid(items)
    qtbot.wait(400)  # first layout + debounced column adapt settle

    gv = w._grid_view
    assert gv.width() == w._content_stack.width()
    cols_before = gv.grid_columns
    sizes_before = _geometry(gv, items)
    cards_before = {str(it.path): id(gv.card_for(it.path)) for it in items}
    gv.apply_selection({items[0].path, items[3].path})
    scroll = gv.scroll_area.verticalScrollBar()
    scroll.setValue(min(120, scroll.maximum()))

    # LIVE TRIGGER: the folder load starts the analysis and covers the stack
    # with the scanning surface while the grid stays shown with spinning
    # badges — the frames the owner resized in.
    w.set_scanning(0, len(items))
    assert w._content_stack.currentWidget() is not gv
    assert gv.isVisible(), "set_scanning must keep the cards on screen"

    w.resize(1900, 800)
    qtbot.wait(600)

    # The grid followed the window ...
    assert gv.width() == w._content_stack.width()
    assert gv.grid_columns > cols_before
    sizes_after = _geometry(gv, items)
    moved = [p for p, rect in sizes_before.items() if sizes_after[p] != rect]
    assert moved, "cards stayed glued to their pre-resize geometry during the run"

    # ... with the SAME widgets (a reflow, never a rebuild) ...
    assert {str(it.path): id(gv.card_for(it.path)) for it in items} == cards_before
    # ... the same display order (sorting waits for the final rank) ...
    assert _display_order(gv, items) == [str(it.path) for it in items]
    # ... and the live scroll/selection untouched.
    assert scroll.value() == min(120, scroll.maximum())
    assert {str(p) for p in gv._selection} == {str(items[0].path), str(items[3].path)}

    # When the analysis lands the grid becomes the current page again and the
    # resize keeps working (the pre-fix "free again" state is not a trade).
    w.set_triage_done()
    w._content_stack.setCurrentWidget(gv)
    w.resize(1000, 800)
    qtbot.wait(600)
    assert gv.width() == w._content_stack.width()
    assert gv.grid_columns < gv._applied_columns or gv.grid_columns == 4


def test_a_resize_replans_the_series_layout_without_restamping_cards(
    qtbot, monkeypatch
) -> None:
    """The series reflow is geometry-only: no per-card content refresh."""
    from tabs.image_gallery.ui.grid_view import series as series_mod

    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1400, 800)
    w.show()
    items = _items(40)
    w.rebuild_grid(items)
    qtbot.wait(300)
    gv = w._grid_view
    gv.set_series([items[:30]], hub_names=["HUB-A"], collapsed={})
    qtbot.wait(300)

    restamps: list[str] = []
    real = series_mod.update_gallery_card

    def _counted(card, item, *a, **kw):
        restamps.append(str(getattr(item, "path", "")))
        return real(card, item, *a, **kw)

    monkeypatch.setattr(series_mod, "update_gallery_card", _counted)
    cols_before = gv.grid_columns
    sizes_before = _geometry(gv, items)

    w.resize(1900, 800)
    qtbot.wait(600)

    assert gv.grid_columns > cols_before
    sizes_after = _geometry(gv, items)
    moved = [p for p, rect in sizes_before.items() if sizes_after[p] != rect]
    assert moved, "series cards stayed glued to their pre-resize geometry"
    assert restamps == [], "a resize re-stamped card content instead of moving geometry"
    # Order inside the series section is untouched (bands interleave rows, so
    # the reading-order check belongs to that section, not to the whole grid).
    assert _display_order(gv, items[:30]) == [str(it.path) for it in items[:30]]
    assert _display_order(gv, items[30:]) == [str(it.path) for it in items[30:]]


def test_a_resize_does_not_turn_a_chunked_build_into_a_full_build(qtbot) -> None:
    """A resize landing mid-build keeps the chunks; it never pulls the pool in."""
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1400, 800)
    w.show()
    qtbot.wait(200)
    items = _items(200)
    w.rebuild_grid(items)
    gv = w._grid_view
    assert gv._rebuild_pending is not None, "200 items must take the chunked path"
    built = len(gv._cards_by_path)

    w.resize(1900, 800)
    assert gv._compute_columns() != gv.grid_columns  # the resize did reach the grid
    gv._adapt_columns_and_reflow()  # the adapt timer's slot, run synchronously

    assert gv._rebuild_pending is not None, "the resize dropped the in-flight build"
    assert len(gv._cards_by_path) <= built + gv._REBUILD_CHUNK, (
        "the resize pulled the whole pool in synchronously"
    )

    qtbot.wait(700)
    assert len(gv._cards_by_path) == len(items), "the chunked build never finished"
