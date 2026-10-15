"""Reusing an UNGROUPED header slot for a series must not emit a warning.

Falsification (pre-fix): the UNGROUPED tail header is built WITHOUT a
``customContextMenuRequested`` connection, but ``_retitle_header`` called
``disconnect()`` on it unconditionally. PySide6 reports the unconnected
disconnect as a ``RuntimeWarning`` (not an exception, so the surrounding
``except Exception`` did not catch it). The guard now only disconnects a
signal this code actually wired (``_gallery_ctx_menu_wired``).
"""

from __future__ import annotations

import warnings
from pathlib import Path

from sli_ui_toolkit.widgets import Button

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.widget import ImageGalleryWidget


def _items(n: int) -> list[GalleryItem]:
    return [GalleryItem(path=Path(f"/gallery/r-{i:02d}.png"), mtime_ns=i + 1) for i in range(n)]


def _ungrouped_header(gv):
    return next(
        (h for h in gv._series_headers if h.objectName() == "GallerySeriesHeader_ungrouped"),
        None,
    )


def test_retitle_ungrouped_slot_for_series_does_not_warn(qtbot) -> None:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1600, 900)
    w.show()
    gv = w._grid_view
    gv.rebuild_grid(_items(3), flat_ungrouped=True)

    hdr = _ungrouped_header(gv)
    assert hdr is not None, "no UNGROUPED header after flat promotion"
    btn = hdr.findChild(Button)
    assert btn is not None
    assert not getattr(btn, "_gallery_ctx_menu_wired", False), "ungrouped slot must be unwired"

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        gv._retitle_header(hdr, "Series A", 0, False)

    bad = [str(x.message) for x in caught if "Failed to disconnect" in str(x.message)]
    assert not bad, bad
    # The slot is a series now: its context menu is (re)wired, flag set.
    assert getattr(btn, "_gallery_ctx_menu_wired", False) is True
