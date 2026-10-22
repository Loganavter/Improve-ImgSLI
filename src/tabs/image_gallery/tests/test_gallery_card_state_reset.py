"""Card state never survives a mode switch, a recycle, or a second row.

Owner report 2026-10-22: "badges and any other card state must reset on a
grid/list switch and when a second row appears". Three measured defects:

1. **List rows were refreshed with the GRID updater** inside the series rebuild
   (``series.py`` kept-card branch): a row has no ``cover`` region, so the update
   raised and the swallowed exception left the inline badge (``#2``/``★``/``✕``)
   stale after the badge had actually changed. The sibling refreshers
   (``marquee.refresh_card`` / ``refresh_cards``) already branch on the mode —
   this file pins that the rebuild does too.
2. **A recycled card kept its selection stamp**: ``_recycle_card`` cleared the
   tint by painting "unselected" but left ``_gallery_sel_applied`` at
   ``(True, accent)``, so the idempotence stamp in ``apply_selection`` skipped
   a genuinely selected item and it rendered unselected.
3. **List rows never cleared the grid pill cache** (``_gallery_badge``): safe
   only while the pool never mixes modes; cleared now with the rest.

All three are real-widget tests (offscreen): the widget, its pool and its series
rebuild are the production ones.
"""

from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.widget import ImageGalleryWidget


def _items(*names: str) -> list[GalleryItem]:
    return [GalleryItem(path=Path(f"/gallery/{n}"), mtime_ns=i + 1) for i, n in enumerate(names)]


def _row_text(card) -> str:
    try:
        return " ".join(str(getattr(r, "text", "")) for r in card.region("text").rows)
    except Exception:
        return ""


def _row_badge(card) -> str:
    text = _row_text(card)
    for token in ("★ BEST", "#2", "#1", "#3", "✕"):
        if token in text:
            return token
    return ""


def _list_widget(qtbot, items: list[GalleryItem]) -> ImageGalleryWidget:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1200, 700)
    w.rebuild_grid(items)
    gv = w._grid_view
    gv.set_series([items[:2]], hub_names=["hub1"], collapsed={})
    w._on_view_toggled(True)
    return w


# -- 1. a list row's badge follows the model through a series rebuild ---------


def test_list_row_badge_is_refreshed_by_the_series_rebuild(qtbot) -> None:
    items = _items("a.png", "b.png", "c.png")
    w = _list_widget(qtbot, items)
    gv = w._grid_view
    card = gv.card_for(items[0].path)
    assert card is not None and "#2" not in _row_text(card)

    # The model gains a rank (what a fusion/Jev pass does), the layout rebuilds
    # the series (what a second row / regroup does).
    items[0].rank = 2
    items[0].badge = "#2"
    gv._rebuild_series()

    text = _row_text(gv.card_for(items[0].path))
    assert "#2" in text, f"stale list row after a series rebuild: {text!r}"


def test_list_row_badge_is_cleared_by_the_series_rebuild(qtbot) -> None:
    """The mirror direction: a badge that goes away must actually go away."""
    items = _items("a.png", "b.png", "c.png")
    w = _list_widget(qtbot, items)
    gv = w._grid_view
    items[0].rank = 2
    items[0].badge = "#2"
    gv._rebuild_series()
    assert "#2" in _row_text(gv.card_for(items[0].path))

    items[0].rank = 0
    items[0].badge = ""
    gv._rebuild_series()
    text = _row_text(gv.card_for(items[0].path))
    assert "#2" not in text, f"stale badge survived the rebuild: {text!r}"


# -- 2. a recycled card is selectable again ----------------------------------


def test_recycled_card_shows_the_selection_tint(qtbot) -> None:
    items = _items("a.png", "b.png")
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1200, 700)
    w.rebuild_grid(items)
    gv = w._grid_view
    target = str(items[0].path)
    gv.apply_selection({target})
    card = gv.card_for(items[0].path)
    assert card is not None and card.is_bg_locked(), "fixture: the card is selected"

    # Recycle it (filter / regroup / append) and take the SAME widget back from
    # the pool, which is what happens for every card after a scroll/mode churn.
    gv._recycle_card(target)
    assert card in list(gv._pool), "fixture: the card went to the pool"
    assert getattr(card, "_gallery_sel_applied", None) is None, (
        "the recycle cleared the tint but left the 'already selected' stamp: "
        "the next selection sweep will skip this card"
    )
    fresh = gv._acquire_card(items[0])
    gv._cards_by_path[target] = fresh
    gv.apply_selection({target})

    assert fresh.is_bg_locked(), (
        "a selected item rendered unselected after its card was recycled: the "
        "selection stamp survived the clear"
    )


# -- 3. grid -> list -> grid keeps the pill but never a stale one ------------


def test_grid_pill_survives_a_mode_round_trip_only_while_it_is_the_model(qtbot) -> None:
    items = _items("a.png", "b.png")
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1200, 700)
    w.rebuild_grid(items, )
    gv = w._grid_view
    items[0].badge = "#2"
    items[0].rank = 2
    w.refresh_card(items[0])
    card = gv.card_for(items[0].path)
    assert getattr(card, "_gallery_badge", None) == "#2"

    w._on_view_toggled(True)
    row = gv.card_for(items[0].path)
    assert "#2" in _row_text(row)

    # The model drops the rank while in list mode; back in grid the pill must
    # not be resurrected from the row's widget memory.
    items[0].badge = ""
    items[0].rank = 0
    w.refresh_card(items[0])
    w._on_view_toggled(False)
    grid_card = gv.card_for(items[0].path)
    assert getattr(grid_card, "_gallery_badge", None) in (None, ""), (
        "a cleared badge came back after a grid<-list round trip"
    )
