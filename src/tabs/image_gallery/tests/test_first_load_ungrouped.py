"""First load must show images under UNGROUPED on the first frame.

Regression: ``widget.rebuild_grid`` painted a flat, header-less grid and the
``UNGROUPED`` section only appeared once the triage worker delivered
``set_triage`` — the very first images (small drop / folder) read as a
nameless group for a frame. All items belong under UNGROUPED from the first
paint.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.widget import ImageGalleryWidget


def _items(*names: str) -> list[GalleryItem]:
    return [GalleryItem(path=Path(f"/gallery/{n}"), mtime_ns=i) for i, n in enumerate(names)]


def _has_ungrouped_header(gv) -> bool:
    for hdr in list(getattr(gv, "_series_headers", []) or []):
        try:
            if hdr.objectName() == "GallerySeriesHeader_ungrouped":
                return True
        except Exception:
            continue
    return False


def test_first_load_shows_ungrouped_header_same_frame(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()

    w.rebuild_grid(_items("a.png", "b.png", "c.png"))
    QApplication.processEvents()

    gv = w._grid_view
    assert gv._series is not None, "flat pool must be promoted to UNGROUPED"
    assert _has_ungrouped_header(gv), "UNGROUPED header must exist on first paint"
    assert [str(m.path) for m in gv._ungrouped] == [str(i.path) for i in _items("a.png", "b.png", "c.png")]
    w.hide()


def test_ungrouped_header_survives_a_later_series_less_triage(qtbot) -> None:
    """A triage delivery with no clusters keeps the UNGROUPED view (no flash)."""
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()

    items = _items("a.png", "b.png")
    w.rebuild_grid(items)
    w.set_triage([], None, None)
    QApplication.processEvents()

    gv = w._grid_view
    assert _has_ungrouped_header(gv)
    w.hide()
