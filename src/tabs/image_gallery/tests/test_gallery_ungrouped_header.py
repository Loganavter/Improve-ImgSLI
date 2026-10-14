"""The UNGROUPED tail header is a normal, collapsible group.

Falsification (pre-fix): ``is_collapsible = index is not None`` built the
UNGROUPED header disabled, with no collapse arrow and a dead click — so while
clustering ran (the provisional pool) the top header was a glyph-less,
non-clickable button. This asserts the header is enabled and that clicking it
toggles the tail collapse (cards leave the layout).
"""

from __future__ import annotations

from pathlib import Path

from sli_ui_toolkit.widgets import Button

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.widget import ImageGalleryWidget


def _items(n: int) -> list[GalleryItem]:
    return [GalleryItem(path=Path(f"/gallery/u-{i:02d}.png"), mtime_ns=i + 1) for i in range(n)]


def _ungrouped_header(gv):
    return next(
        (h for h in gv._series_headers
         if h.objectName() == "GallerySeriesHeader_ungrouped"),
        None,
    )


def test_ungrouped_header_is_enabled_and_collapsible(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1600, 900)
    w.show()
    gv = w._grid_view
    gv.rebuild_grid(_items(4), flat_ungrouped=True)

    hdr = _ungrouped_header(gv)
    assert hdr is not None, "no UNGROUPED header after flat promotion"
    btn = hdr.findChild(Button)
    assert btn is not None
    assert btn.isEnabled(), "UNGROUPED header button is a dead (disabled) control"

    cards_before = gv.items_layout.count()
    gv._toggle_collapse(None)
    assert getattr(gv, "_tail_collapsed", False) is True
    # Collapsed tail: only the header row remains in the layout.
    assert gv.items_layout.count() < cards_before
