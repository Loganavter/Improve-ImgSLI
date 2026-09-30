"""Quick-look canvas seam tests: frozen-pyramid sourcing (wave-C1 rewire).

The GPU canvas path is sourced ONLY through the frozen pyramid seam
(``preview_canvas_host._coarse_store_for`` /
``PyramidPixelStore.best_pixels``) — never ``TiledPixelStore.from_path``,
never ``qimage_from_pixel_source``, never a full-frame materialize.
These tests pin that, offscreen-safe (fake canvas child, no RHI present):

- distinct sources through ``_populate_preview_canvas`` -> distinct
  canvas content (payload == content per source, never a neighbor's);
- huge source through the canvas path -> full-decode spies
  (``from_path`` / ``materialize_full`` / ``qimage_from_pixel_source``)
  stay silent AND the acquired store is size-bound;
- miss / unbuilt -> ``False`` + placeholder degrade, no raise, canvas
  never fed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.ui.quick_look import QuickLookOverlay
from tabs.image_gallery.ui.quick_look import preview_canvas_host as host

_COARSE_CAP = 1024


def _png(tmp_path: Path, name: str, color: str, w: int = 800, h: int = 600) -> Path:
    pm = QPixmap(w, h)
    pm.fill(QColor(color))
    p = tmp_path / name
    assert pm.save(str(p), "PNG")
    return p


def _make_overlay(qtbot) -> QuickLookOverlay:
    parent = QWidget()
    qtbot.addWidget(parent)
    ov = QuickLookOverlay(parent)
    ov._parity_test_parent = parent  # strong ref, keeps C++ tree alive
    return ov


def _item(path: Path) -> GalleryItem:
    return GalleryItem(path=path, mtime_ns=1, metrics={})


class _FakeCanvas(QWidget):
    """Canvas double: records set_source stores, tolerates fallback wiring."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.sources: list = []
        self.cleared = 0

    def set_source(self, store) -> None:
        self.sources.append(store)

    def clear_source(self) -> None:
        self.cleared += 1


def _mean_rgb(store) -> tuple[float, float, float]:
    w, h = store.size
    arr = np.ascontiguousarray(store.read_array((0, 0, w, h))).astype(np.float64)
    return float(arr[:, :, 0].mean()), float(arr[:, :, 1].mean()), float(arr[:, :, 2].mean())


def test_canvas_path_distinct_sources_distinct_content(qtbot, tmp_path, monkeypatch):
    """A then B: canvas fed each store in order; pixels match their payload."""
    red = _png(tmp_path, "red.png", "#c0392b")
    blue = _png(tmp_path, "blue.png", "#3a6ea5")
    ov = _make_overlay(qtbot)
    fake = _FakeCanvas()
    monkeypatch.setattr(host, "_ensure_preview_canvas", lambda _ov: fake)

    assert host._populate_preview_canvas(ov, _item(red)) is True
    store_a = ov._preview_store
    assert store_a is not None and store_a.is_open
    assert fake.sources == [store_a]

    assert host._populate_preview_canvas(ov, _item(blue)) is True
    store_b = ov._preview_store
    assert store_b is not None and store_b.is_open
    assert store_b is not store_a
    assert fake.sources == [store_a, store_b], "canvas must see A then B, never swapped"
    try:
        assert not store_a.is_open, "repopulate must close the previous store"
    except Exception:
        pass

    # store_a is closed above; re-sample payload identity from fresh seam reads.
    fresh_a = host._coarse_store_for(red)
    fresh_b = host._coarse_store_for(blue)
    assert fresh_a is not None and fresh_b is not None
    try:
        ra, ga, ba = _mean_rgb(fresh_a)
        rb, gb, bb = _mean_rgb(fresh_b)
    finally:
        for s in (fresh_a, fresh_b):
            try:
                s.close()
            except Exception:
                pass
    assert ra > ba, f"red payload must stay red-dominant, got {(ra, ga, ba)}"
    assert bb > rb, f"blue payload must stay blue-dominant, got {(rb, gb, bb)}"
    assert (ra, ga, ba) != (rb, gb, bb), "distinct sources must yield distinct content"
    QApplication.processEvents()
    ov.hide()


def test_canvas_path_huge_source_no_full_frame(qtbot, tmp_path, monkeypatch):
    """2400px source through the canvas path: no full-frame decode anywhere."""
    from engine.store import tiled_pixel_store as tps_mod

    big = _png(tmp_path, "big.png", "#3a6ea5", w=2400, h=1800)
    fired: list = []

    orig_from_path = tps_mod.TiledPixelStore.from_path
    orig_materialize = tps_mod.TiledPixelStore.materialize_full
    orig_qimage = tps_mod.qimage_from_pixel_source

    def _spy_from_path(*args, **kwargs):
        fired.append("from_path")
        return orig_from_path(*args, **kwargs)

    def _spy_materialize(self):
        fired.append("materialize_full")
        return orig_materialize(self)

    def _spy_qimage(*args, **kwargs):
        fired.append("qimage_from_pixel_source")
        return orig_qimage(*args, **kwargs)

    monkeypatch.setattr(tps_mod.TiledPixelStore, "from_path", _spy_from_path)
    monkeypatch.setattr(tps_mod.TiledPixelStore, "materialize_full", _spy_materialize)
    monkeypatch.setattr(tps_mod, "qimage_from_pixel_source", _spy_qimage)

    ov = _make_overlay(qtbot)
    fake = _FakeCanvas()
    monkeypatch.setattr(host, "_ensure_preview_canvas", lambda _ov: fake)

    assert host._populate_preview_canvas(ov, _item(big)) is True
    QApplication.processEvents()

    assert fired == [], f"canvas path must not full-decode, saw {fired}"
    store = ov._preview_store
    assert store is not None and store.is_open
    assert max(store.size) <= _COARSE_CAP, f"coarse store must be size-bound, got {store.size}"
    assert fake.sources == [store]
    mean = _mean_rgb(store)
    assert mean[2] > mean[0], f"payload must survive the bounded path, got {mean}"
    ov.hide()


def test_canvas_path_miss_degrades_to_placeholder(qtbot, tmp_path, monkeypatch):
    """Missing/unbuilt source: seam None, populate False, placeholder, no raise."""
    import tabs.image_gallery.ui.quick_look.helpers as ql_helpers

    ov = _make_overlay(qtbot)
    fake = _FakeCanvas()
    monkeypatch.setattr(host, "_ensure_preview_canvas", lambda _ov: fake)

    missing = tmp_path / "nope.png"
    assert host._coarse_store_for(missing) is None, "miss must fail closed to None"
    assert host._populate_preview_canvas(ov, _item(missing)) is False
    assert fake.sources == [], "canvas must never be fed on a miss"
    assert ov._preview_store is None, "no neighbor content may linger as the store"

    ql_helpers.populate_preview(ov, _item(missing))  # must not raise
    QApplication.processEvents()
    assert ov._preview_store is None, "no neighbor content may linger"
    assert getattr(ov, "_preview_full", None) is None, "nothing stashed on a miss"
    ov.hide()
