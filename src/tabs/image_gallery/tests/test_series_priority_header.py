"""Cross-series routing hint renders a visible marker on the series header.

Task ``task-gallery-ai-routing-jev-2026-10-09`` (S2): the Jev priority hint is
additive — it must surface on the series HEADER (which series needs a human
first) and never touch cards, ranks or the selection. Falsification: a hint that
does not appear, an absent hint that does, or a marker that survives a clear.
"""

from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.widget import ImageGalleryWidget


def _items(*names: str) -> list[GalleryItem]:
    return [GalleryItem(path=Path(f"/gallery/{n}"), mtime_ns=i) for i, n in enumerate(names)]


def _header_btn_text(btn) -> str:
    try:
        region = btn.region("_main")
        rows = getattr(region, "rows", None) or getattr(region, "_rows", None) or []
        if rows:
            return str(getattr(rows[0], "text", ""))
    except Exception:
        pass
    return ""


def _header_text(gv) -> str:
    btn = gv.findChild(object, "GallerySeriesHeaderBtn_0")
    assert btn is not None
    return _header_btn_text(btn)


def test_series_attention_marker_toggles_on_the_header(qtbot) -> None:
    items = _items("a.png", "b.png", "c.png")
    for it in items:
        it.series_id = "series_7"
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()
    w.rebuild_grid(items)
    gv = w._grid_view
    gv.set_series([items], hub_names=["HUB-A"], collapsed={})

    # No hint yet → no marker.
    assert "NEEDS ATTENTION" not in _header_text(gv)

    # Flagged series → the header shows the marker (additive, visible).
    w.set_series_attention({"series_7"})
    assert "NEEDS ATTENTION" in _header_text(gv)

    # A different series id does not mark THIS header.
    w.set_series_attention({"series_OTHER"})
    assert "NEEDS ATTENTION" not in _header_text(gv)

    # Clearing removes it.
    w.set_series_attention({"series_7"})
    w.set_series_attention(set())
    assert "NEEDS ATTENTION" not in _header_text(gv)


def test_series_attention_never_touches_rank_or_selection(qtbot) -> None:
    items = _items("a.png", "b.png")
    for it in items:
        it.series_id = "series_1"
    items[0].rank, items[0].rank_source = 2, "fusion"
    items[1].rank, items[1].rank_source = 1, "fusion"
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()
    w.rebuild_grid(items)
    w._grid_view.set_series([items], hub_names=["HUB"], collapsed={})

    w.set_series_attention({"series_1"})

    assert [it.rank for it in items] == [2, 1]
    assert [it.rank_source for it in items] == ["fusion", "fusion"]
