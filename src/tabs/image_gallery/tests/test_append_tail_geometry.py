"""Appended cards continue the UNGROUPED tail block in place.

Regression: ``append_new_cards`` continued from ``rowCount()``, which
counts header rows too — the 2nd card of a live pool landed a row low on
its own (live: reads as a nameless group until triage rebuilds). New
cards must continue the tail block row math (same as ``_rebuild_series``).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.widget import ImageGalleryWidget


def _items(*names: str) -> list[GalleryItem]:
    return [GalleryItem(path=Path(f"/gallery/{n}"), mtime_ns=i) for i, n in enumerate(names)]


def _pos(gv, item) -> tuple[int, int]:
    card = gv.card_for(item.path)
    assert card is not None
    idx = gv.items_layout.indexOf(card)
    assert idx >= 0
    r, c, _, _ = gv.items_layout.getItemPosition(idx)
    return int(r), int(c)


def test_appended_second_card_sits_beside_first(qtbot) -> None:
    """1 live ungrouped card + 1 drop → same row, adjacent columns."""
    a, b = _items("a.png", "b.png")
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()
    w.rebuild_grid([a])
    gv = w._grid_view
    gv.set_series([], hub_names=[], collapsed={})  # live UNGROUPED view (post-triage-1)
    QApplication.processEvents()
    QApplication.processEvents()
    assert gv._series is not None
    cols = max(1, int(gv.grid_columns))
    gv.append_new_cards([b])
    QApplication.processEvents()
    ra, ca = _pos(gv, a)
    rb, cb = _pos(gv, b)
    assert ca == 0
    assert (rb, cb) == (ra + (1 // cols), 1 % cols)
    w.hide()


def test_appended_card_continues_tail_below_series(qtbot) -> None:
    """Series above + 1 ungrouped + 1 drop → new card continues the tail block."""
    a1, a2, c, d = _items("a1.png", "a2.png", "c.png", "d.png")
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()
    w.rebuild_grid([a1, a2, c])
    gv = w._grid_view
    gv.set_series([[a1, a2]], hub_names=["HUB-A"], collapsed={})
    assert [str(m.path) for m in gv._ungrouped] == [str(c.path)]
    QApplication.processEvents()
    QApplication.processEvents()
    cols = max(1, int(gv.grid_columns))
    rc, cc = _pos(gv, c)
    gv.append_new_cards([d])
    QApplication.processEvents()
    rd, cd = _pos(gv, d)
    # d is ungrouped position 1 → same block math as a full rebuild.
    assert (rd, cd) == (rc + (1 // cols), 1 % cols)
    w.hide()
