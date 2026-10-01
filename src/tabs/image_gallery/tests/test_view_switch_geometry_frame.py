"""Switching grid<->list must not flash stale/overlapping rows.

User report (2026-10-01): switching the gallery view mode (cards <-> list)
showed the same one-frame artifact as the series-expand bug — old/overlapping
rows with the wrong text painted for one frame, then snapped correct.

Root cause (same family as test_series_collapse_expand_artifact): the flat
``rebuild_grid`` re-adds cards with ``addWidget``/``show`` but never commits the
new geometry synchronously, so the previous mode's widgets keep their stale
rects for the next event-loop turn and paint over the new ones.

Asserts ``payload(i) == content(i)`` per visible card (region pixmap == its own
item's thumbnail) and unique, non-overlapping positions immediately after the
switch, with NO extra event-loop turn.
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
    if pm is None:
        return None
    try:
        if pm.isNull():
            return None
    except Exception:
        return None
    img = pm.toImage()
    return (int(img.cacheKey()), img.pixelColor(0, 0).name())


def _cover_region_id(gv) -> str:
    return "thumb" if getattr(gv, "_view_mode", "grid") == "list" else "cover"


def _visible_cards(gv) -> list:
    out = []
    for path in list(gv._cards_by_path):
        card = gv._cards_by_path.get(path)
        if card is not None and card.isVisible():
            out.append((path, card))
    return out


def _assert_content_identity(gv, items) -> None:
    own = {str(it.path): _pixmap_signature(it.thumbnail) for it in items}
    rid = _cover_region_id(gv)
    for path, card in _visible_cards(gv):
        region = card.region(rid).pixmap
        assert _pixmap_signature(region) == own[path], (
            f"card {path} paints {rid} {_pixmap_signature(region)} "
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
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            pa, ra = rects[i]
            pb, rb = rects[j]
            assert not ra.intersects(rb), (
                f"cards {pa} {ra.getRect()} and {pb} {rb.getRect()} overlap"
            )


def test_view_mode_switch_has_no_stale_or_overlapping_card(qtbot) -> None:
    from PySide6.QtWidgets import QApplication

    series_items = [_item("a.png", _COLORS[0]), _item("b.png", _COLORS[1])]
    tail_items = [_item("c.png", _COLORS[2]), _item("d.png", _COLORS[3])]
    items = series_items + tail_items

    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()
    w.rebuild_grid(items)
    gv = w._grid_view
    gv.set_series([series_items], hub_names=["HUB-A"], collapsed={})
    QApplication.processEvents()

    # grid -> list: NO extra event-loop turn, next frame must be correct.
    gv.set_view_mode("list")
    _assert_content_identity(gv, items)
    _assert_no_overlap_and_unique_positions(gv)

    QApplication.processEvents()
    _assert_content_identity(gv, items)
    _assert_no_overlap_and_unique_positions(gv)

    # list -> grid: same contract.
    gv.set_view_mode("grid")
    _assert_content_identity(gv, items)
    _assert_no_overlap_and_unique_positions(gv)

    QApplication.processEvents()
    _assert_content_identity(gv, items)
    _assert_no_overlap_and_unique_positions(gv)
