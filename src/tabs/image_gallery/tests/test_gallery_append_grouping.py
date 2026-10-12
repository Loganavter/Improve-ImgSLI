"""Append groups the fresh card immediately and never repositions twice.

Bug 2 (first-drop grouping delay): dropping a single image left its card
flat (no UNGROUPED header) until the triage worker delivered. The append
fast-path only handled the case where a series/ungrouped view was already
live, so the very first growth of a pre-triage pool stayed header-less.
A pre-triage pool is now promoted to one UNGROUPED section in the same
pass as the append.

Bug 3 (double reposition): dropping a non-matching image into a pool that
already had a series placed the card once via the append fast-path and
then the triage delivery re-ran ``set_series`` and tore the whole grid
down a second time. The regroup now converges to a no-op when the target
plan already matches the live layout.

The base tail-anchor row math (``test_append_tail_geometry.py``) is kept.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtWidgets import QApplication

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.widget import ImageGalleryWidget

_LOGGER_NAME = "ImproveImgSLI"


def _items(*names: str) -> list[GalleryItem]:
    return [GalleryItem(path=Path(f"/gallery/{n}"), mtime_ns=i) for i, n in enumerate(names)]


def _pos(gv, item) -> tuple[int, int]:
    card = gv.card_for(item.path)
    assert card is not None
    idx = gv.items_layout.indexOf(card)
    assert idx >= 0
    r, c, _, _ = gv.items_layout.getItemPosition(idx)
    return int(r), int(c)


def _tail_headers(gv) -> list:
    return [
        h
        for h in list(getattr(gv, "_series_headers", []) or [])
        if getattr(h, "objectName", lambda: "")() == "GallerySeriesHeader_ungrouped"
    ]


class _LayoutWrites:
    """Count real grid mutations (``takeAt`` + ``addWidget``) on the layout."""

    def __init__(self, gv) -> None:
        self.gv = gv
        self.take = 0
        self.add = 0

    def __enter__(self):
        layout = self.gv.items_layout
        self._orig_take = layout.takeAt
        self._orig_add = layout.addWidget

        def take(*a, **k):
            self.take += 1
            return self._orig_take(*a, **k)

        def add(*a, **k):
            self.add += 1
            return self._orig_add(*a, **k)

        layout.takeAt = take
        layout.addWidget = add
        return self

    def __exit__(self, *exc) -> None:
        layout = self.gv.items_layout
        layout.takeAt = self._orig_take
        layout.addWidget = self._orig_add


def _append_errors(caplog) -> list:
    """Swallowed exceptions logged from the append/regroup paths."""
    out = []
    for rec in caplog.records:
        if not rec.exc_info:
            continue
        msg = rec.getMessage()
        if "append_new_cards" in msg or "_rebuild_series" in msg:
            out.append(rec)
    return out


def test_first_append_groups_into_ungrouped(qtbot, caplog) -> None:
    """Bug 2: empty → rebuild([a]) → rebuild([a,b]) groups both, no triage."""
    caplog.set_level(logging.DEBUG, logger=_LOGGER_NAME)
    a, b = _items("a.png", "b.png")
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()
    w.rebuild_grid([a])
    gv = w._grid_view
    assert gv._series == []  # already UNGROUPED from the first load

    with _LayoutWrites(gv) as lw:
        w.rebuild_grid([a, b])
    QApplication.processEvents()

    assert lw.add > 0  # the append places the fresh tail card (no full reflow)
    assert gv._series == []
    assert [str(x.path) for x in gv._ungrouped] == [str(a.path), str(b.path)]
    headers = _tail_headers(gv)
    assert len(headers) == 1  # exactly one UNGROUPED header, no triage pass
    ra, ca = _pos(gv, a)
    rb, cb = _pos(gv, b)
    hrow = gv._row_of(headers[0])
    assert hrow is not None
    assert ra == rb == hrow + 1  # both cards sit in the tail, under the header
    assert ca == 0 and cb == 1
    assert _append_errors(caplog) == []
    w.hide()


def test_append_after_series_single_reposition(qtbot, caplog) -> None:
    """Bug 3: one series + non-matching append repositions exactly once."""
    caplog.set_level(logging.DEBUG, logger=_LOGGER_NAME)
    a1, a2, c, d = _items("a1.png", "a2.png", "c.png", "d.png")
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()
    w.rebuild_grid([a1, a2, c])
    gv = w._grid_view
    gv.set_series([[a1, a2]], hub_names=["HUB-A"], collapsed={})
    QApplication.processEvents()
    before = {str(it.path): _pos(gv, it) for it in (a1, a2, c)}

    with _LayoutWrites(gv) as lw:
        w.rebuild_grid([a1, a2, c, d])
    QApplication.processEvents()
    assert lw.add > 0  # append placed the fresh card (the one reposition)
    d_row, d_col = _pos(gv, d)
    c_row, c_col = _pos(gv, c)
    assert (d_row, d_col) == (c_row, c_col + 1)  # continues the tail block
    for it in (a1, a2, c):
        assert _pos(gv, it) == before[str(it.path)]  # existing cards untouched

    # The triage delivery that follows must converge, not jump a second time.
    with _LayoutWrites(gv) as second:
        w.set_triage([[a1, a2]], "camera", None)
    QApplication.processEvents()
    assert second.take == 0 and second.add == 0
    for it in (a1, a2, c, d):
        assert gv.card_for(it.path) is not None
    assert [str(x.path) for x in gv._ungrouped] == [str(c.path), str(d.path)]
    assert _append_errors(caplog) == []
    w.hide()


def test_append_into_series_only_creates_tail(qtbot) -> None:
    """Bug 3 (no existing tail): a non-matching append creates UNGROUPED once."""
    a1, a2, c = _items("a1.png", "a2.png", "c.png")
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()
    w.rebuild_grid([a1, a2])
    gv = w._grid_view
    gv.set_series([[a1, a2]], hub_names=["HUB-A"], collapsed={})
    QApplication.processEvents()
    assert _tail_headers(gv) == []

    with _LayoutWrites(gv) as lw:
        w.rebuild_grid([a1, a2, c])
    QApplication.processEvents()
    assert lw.add > 0
    headers = _tail_headers(gv)
    assert len(headers) == 1
    hrow = gv._row_of(headers[0])
    assert hrow is not None
    assert _pos(gv, c) == (hrow + 1, 0)
    assert [str(x.path) for x in gv._ungrouped] == [str(c.path)]

    with _LayoutWrites(gv) as second:
        w.set_triage([[a1, a2]], "camera", None)
    QApplication.processEvents()
    assert second.take == 0 and second.add == 0
    w.hide()
