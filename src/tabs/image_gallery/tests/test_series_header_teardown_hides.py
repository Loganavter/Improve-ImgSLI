"""Teardown must hide series headers BEFORE dropping their parent.

Root cause of the per-switch global busy cursor on Wayland: a still-visible
header reparented to None instantly maps its own top-level window (fresh
wl_surface + xdg_toplevel + activation token with the stale click serial)
for the ms until deleteLater fires. The token can never be consumed, so
Mutter holds the global busy cursor until the startup-sequence timeout.

Single-series/flat pools never showed it: card recycle hides cards before
reparenting, and flat pools have no headers at all.

Contract: every header removed by the teardown paths is hidden
synchronously — a hidden widget never maps a toplevel, so no surface and
no activation request can escape.
"""

from __future__ import annotations

from pathlib import Path

import shiboken6
from PySide6.QtGui import QColor, QPixmap

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.widget import ImageGalleryWidget


def _item(name: str, color: str) -> GalleryItem:
    it = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=abs(hash(name)) % 100000)
    pm = QPixmap(16, 16)
    pm.fill(QColor(color))
    it.thumbnail = pm
    return it


def _headers(w):
    return list(getattr(w._grid_view, "_series_headers", []) or [])


def test_switch_to_empty_hides_headers_before_unparenting(qtbot) -> None:
    from PySide6.QtWidgets import QApplication

    colors = ("#ff0000", "#00ff00", "#0000ff", "#ffff00", "#ff00ff")
    items = [_item(f"m-{i}.png", colors[i]) for i in range(5)]

    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()
    w.rebuild_grid(items)
    w._grid_view.set_series([items[:3], items[3:]], hub_names=["HUB-A", "HUB-B"], collapsed={})
    QApplication.processEvents()
    headers = _headers(w)
    assert len(headers) == 2

    # Switch-to-empty view path (clear_to_empty -> reset_session_view).
    w.reset_session_view()

    # Synchronous invariant: removed headers are hidden BEFORE the event
    # loop delivers deleteLater — hidden widgets never map a toplevel.
    for hdr in headers:
        assert hdr.isHidden(), f"{hdr.objectName()} still visible after teardown"

    # Deferred deletes need a spinning loop (bare processEvents does not
    # deliver them in this harness) — then everything must be gone with
    # no orphan toplevel left behind.
    qtbot.wait(100)
    for hdr in headers:
        assert not shiboken6.isValid(hdr)

    stale_toplevels = [
        t
        for t in QApplication.topLevelWidgets()
        if (t.objectName() or "").startswith("GallerySeriesHeader")
    ]
    assert stale_toplevels == []


def test_clear_series_headers_hides_synchronously(qtbot) -> None:
    from PySide6.QtWidgets import QApplication

    colors = ("#ff0000", "#00ff00", "#0000ff")
    items = [_item(f"s-{i}.png", colors[i]) for i in range(3)]

    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()
    w.rebuild_grid(items)
    w._grid_view.set_series([items], hub_names=["HUB-A"], collapsed={})
    QApplication.processEvents()
    headers = _headers(w)
    assert len(headers) == 1

    w._grid_view._clear_series_headers()
    for hdr in headers:
        assert hdr.isHidden()

    qtbot.wait(100)
    for hdr in headers:
        assert not shiboken6.isValid(hdr)
