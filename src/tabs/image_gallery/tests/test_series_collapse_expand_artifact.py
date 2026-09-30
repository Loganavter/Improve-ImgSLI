"""Collapse/expand a SERIES header must not flash a stale/overlapping card.

User report: expanding a collapsed ``SERIES n · … VARIANTS`` header showed a
one-frame artifact — a recycled card painted at a neighbouring card's slot
(wrong payload) / two cards overlapped — then snapped correct one frame later.

Root cause (supervisor theory B): ``_rebuild_series`` re-adds widgets with
``takeAt``/``addWidget`` but never commits the new geometry synchronously.
An already-visible neighbour (the UNGROUPED tail sliding up/down) kept its
stale rect for the next event-loop turn and painted over the freshly
revealed series cards. The fix activates the layout before the next paint.

This test asserts the CONTENT-IDENTITY contract per index (region pixmap ==
its own item's thumbnail, not just a card count) plus non-overlapping
geometry immediately after the toggle, with NO extra event-loop turn.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QPixmap

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.widget import ImageGalleryWidget

_COLORS = ("#ff0000", "#00ff00", "#0000ff", "#ffff00", "#ff00ff", "#00ffff")


def _item(name: str, color: str) -> GalleryItem:
    it = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=abs(hash(name)) % 100000)
    pm = QPixmap(16, 16)
    pm.fill(QColor(color))
    it.thumbnail = pm
    return it


def _pixmap_signature(pm: object) -> object:
    """Content hash of a QPixmap (identity of ``region(...).pixmap`` object)."""
    if pm is None:
        return None
    try:
        if pm.isNull():
            return None
    except Exception:
        return None
    img = pm.toImage()
    return (int(img.cacheKey()), img.pixelColor(0, 0).name())


def _visible_cards(gv) -> list:
    cards = []
    for path in list(gv._cards_by_path):
        card = gv._cards_by_path.get(path)
        if card is not None and card.isVisible():
            cards.append((path, card))
    return cards


def _assert_content_identity(gv, items) -> None:
    own = {str(it.path): _pixmap_signature(it.thumbnail) for it in items}
    for path, card in _visible_cards(gv):
        cover = card.region("cover").pixmap
        assert _pixmap_signature(cover) == own[path], (
            f"card {path} paints cover {_pixmap_signature(cover)} "
            f"but its item owns {own[path]}"
        )


def _assert_no_overlap_and_unique_positions(gv) -> None:
    layout = gv.items_layout
    positions: dict[tuple, str] = {}
    rects: list[tuple[str, object]] = []
    for path, card in _visible_cards(gv):
        idx = layout.indexOf(card)
        assert idx >= 0, f"visible card {path} missing from layout"
        pos = tuple(int(v) for v in layout.getItemPosition(idx))
        assert pos not in positions, (
            f"cards {positions.get(pos)} and {path} share position {pos}"
        )
        positions[pos] = path
        rects.append((path, card.geometry()))
    count = len(rects)
    for i in range(count):
        for j in range(i + 1, count):
            pa, ra = rects[i]
            pb, rb = rects[j]
            assert not ra.intersects(rb), (
                f"cards {pa} {ra.getRect()} and {pb} {rb.getRect()} overlap"
            )


def test_expand_collapsed_series_has_no_stale_or_overlapping_card(qtbot) -> None:
    from PySide6.QtWidgets import QApplication

    series_items = [
        _item("a.png", _COLORS[0]),
        _item("b.png", _COLORS[1]),
        _item("c.png", _COLORS[2]),
    ]
    tail_item = _item("tail.png", _COLORS[3])
    all_items = series_items + [tail_item]

    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()
    w.rebuild_grid(all_items)
    gv = w._grid_view
    gv.set_series([series_items], hub_names=["HUB-A"], collapsed={})
    QApplication.processEvents()

    # Collapse the series (cards are recycled into the pool). Settle the
    # collapsed frame — the user actually sees it before clicking to expand.
    gv._toggle_collapse(0)
    assert gv._collapsed.get(0) is True
    QApplication.processEvents()
    # Expand. NO further event-loop turn: the very next frame must be correct.
    gv._toggle_collapse(0)
    assert gv._collapsed.get(0) is False

    # NO extra event-loop turn: the very next frame must already be correct.
    _assert_content_identity(gv, all_items)
    _assert_no_overlap_and_unique_positions(gv)

    # And it must stay correct once the event loop settles.
    QApplication.processEvents()
    _assert_content_identity(gv, all_items)
    _assert_no_overlap_and_unique_positions(gv)
