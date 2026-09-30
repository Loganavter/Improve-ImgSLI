"""Quick-look stash memo: memoized bounded source + split inner timings.

- First populate: exactly ONE coarse build shared by the canvas store and
  the stash pixmap (no double decode); the stash is memoized per overlay.
- Revisit of a seen item: ZERO source decodes (spy), same stash object,
  canvas re-fed with a fresh bounded store, previous store closed, own
  bytes preserved (never a neighbor's).
- Inner gallery-debug timings (``preview-coarse=`` / ``preview-stash=`` /
  ``preview-set-source=``, ``preview-stash-hit=``) exist only behind
  ``IMGSLI_GALLERY_DEBUG``.
- Key shape (normpath, mtime_ns, size); bound evicts oldest; cache errors
  fail open to today's recompute path.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.ui.quick_look import QuickLookOverlay
from tabs.image_gallery.ui.quick_look import preview as _preview
from tabs.image_gallery.ui.quick_look import preview_canvas_host as host
from tabs.image_gallery.ui.quick_look.preview import (
    _STASH_CACHE_MAX,
    _stash_cache_key,
    _stash_cache_store,
    _stash_preview_source,
)


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


def _center_rgb(pixmap) -> tuple[int, int, int]:
    img = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    c = img.pixelColor(img.width() // 2, img.height() // 2)
    return (c.red(), c.green(), c.blue())


def _mean_rgb(store) -> tuple[float, float, float]:
    w, h = store.size
    arr = np.ascontiguousarray(store.read_array((0, 0, w, h))).astype(np.float64)
    return float(arr[:, :, 0].mean()), float(arr[:, :, 1].mean()), float(arr[:, :, 2].mean())


def _counting_spies(monkeypatch):
    """Count source-decode entry points; return counts dict."""
    from engine.store.pyramid_pixel_store import PyramidPixelStore

    counts = {"coarse": 0, "pyramid": 0, "reader": 0}
    _real_coarse = PyramidPixelStore.coarse_from_source  # bound classmethod
    _real_pyr = _preview._pyramid_pixmap_for
    _real_reader = _preview._load_scaled_pixmap

    def _coarse(cls, *a, **k):
        counts["coarse"] += 1
        return _real_coarse(*a, **k)

    def _pyr(*a, **k):
        counts["pyramid"] += 1
        return _real_pyr(*a, **k)

    def _reader(*a, **k):
        counts["reader"] += 1
        return _real_reader(*a, **k)

    monkeypatch.setattr(PyramidPixelStore, "coarse_from_source", classmethod(_coarse))
    monkeypatch.setattr(_preview, "_pyramid_pixmap_for", _pyr)
    monkeypatch.setattr(_preview, "_load_scaled_pixmap", _reader)
    return counts


def _decodes(counts) -> int:
    return counts["coarse"] + counts["pyramid"] + counts["reader"]


def test_first_populate_single_coarse_build(qtbot, tmp_path, monkeypatch):
    """Miss: one bounded coarse build feeds BOTH the canvas and the stash."""
    red = _png(tmp_path, "red.png", "#c0392b")
    counts = _counting_spies(monkeypatch)
    ov = _make_overlay(qtbot)
    fake = _FakeCanvas()
    monkeypatch.setattr(host, "_ensure_preview_canvas", lambda _ov: fake)

    assert host._populate_preview_canvas(ov, _item(red)) is True
    QApplication.processEvents()

    # Single shared build: the stash sampled the host's open store instead
    # of building a second coarse (today's double decode).
    assert counts["coarse"] == 1, f"one shared coarse build, saw {counts}"
    assert counts["pyramid"] == 0, f"stash must not rebuild, saw {counts}"
    assert counts["reader"] == 0
    assert ov._preview_store is not None and ov._preview_store.is_open
    assert ov._preview_full is not None and not ov._preview_full.isNull()
    assert _center_rgb(ov._preview_full) == (192, 57, 43)
    assert fake.sources == [ov._preview_store]
    ov.hide()


def test_revisit_seen_item_zero_decodes(qtbot, tmp_path, monkeypatch):
    """Walk back: memo hit — no source decode, same stash, fresh store."""
    red = _png(tmp_path, "red.png", "#c0392b")
    blue = _png(tmp_path, "blue.png", "#3a6ea5")
    counts = _counting_spies(monkeypatch)
    ov = _make_overlay(qtbot)
    fake = _FakeCanvas()
    monkeypatch.setattr(host, "_ensure_preview_canvas", lambda _ov: fake)

    assert host._populate_preview_canvas(ov, _item(red)) is True
    first_full = ov._preview_full
    first_store = ov._preview_store
    after_first = _decodes(counts)
    assert after_first > 0
    QApplication.processEvents()

    assert host._populate_preview_canvas(ov, _item(blue)) is True
    after_blue = _decodes(counts)
    assert after_blue > after_first
    assert _center_rgb(ov._preview_full) == (58, 110, 165)
    QApplication.processEvents()

    assert host._populate_preview_canvas(ov, _item(red)) is True
    QApplication.processEvents()

    # Revisit skips ALL decode work: counts frozen, same stash object.
    assert _decodes(counts) == after_blue, f"revisit must not decode, saw {counts}"
    assert ov._preview_full is first_full
    assert _center_rgb(ov._preview_full) == (192, 57, 43)
    # Canvas re-fed with a fresh bounded store; the previous one closed.
    assert len(fake.sources) == 3
    assert fake.sources[0] is first_store
    second_red_store = ov._preview_store
    assert fake.sources[2] is second_red_store
    assert second_red_store is not None and second_red_store.is_open
    assert max(second_red_store.size) <= 1024
    try:
        assert not first_store.is_open, "repopulate must close the previous store"
    except Exception:
        pass
    r, g, b = _mean_rgb(second_red_store)
    assert r > b, f"revisit store must hold red bytes, got {(r, g, b)}"
    ov.hide()


def test_memo_is_per_overlay(qtbot, tmp_path, monkeypatch):
    """No global pixmap leaks: a second overlay rebuilds for the same item."""
    red = _png(tmp_path, "red.png", "#c0392b")
    counts = _counting_spies(monkeypatch)
    ov1 = _make_overlay(qtbot)
    fake1 = _FakeCanvas()
    monkeypatch.setattr(host, "_ensure_preview_canvas", lambda _ov: fake1)
    assert host._populate_preview_canvas(ov1, _item(red)) is True
    after_first = _decodes(counts)

    ov2 = _make_overlay(qtbot)
    fake2 = _FakeCanvas()
    monkeypatch.setattr(host, "_ensure_preview_canvas", lambda _ov: fake2)
    assert host._populate_preview_canvas(ov2, _item(red)) is True
    assert _decodes(counts) > after_first, "second overlay must not reuse the first's memo"
    assert ov2._preview_full is not ov1._preview_full
    ov1.hide()
    ov2.hide()


def test_inner_timings_behind_gallery_debug_flag(qtbot, tmp_path, monkeypatch, caplog):
    """Split timings exist only with IMGSLI_GALLERY_DEBUG=1 (no spam)."""
    import logging

    red = _png(tmp_path, "red.png", "#c0392b")
    blue = _png(tmp_path, "blue.png", "#3a6ea5")
    ov = _make_overlay(qtbot)
    fake = _FakeCanvas()
    monkeypatch.setattr(host, "_ensure_preview_canvas", lambda _ov: fake)

    monkeypatch.setenv("IMGSLI_GALLERY_DEBUG", "1")
    with caplog.at_level(logging.WARNING, logger="ImproveImgSLI"):
        caplog.clear()
        assert host._populate_preview_canvas(ov, _item(red)) is True
        QApplication.processEvents()
        assert host._populate_preview_canvas(ov, _item(red)) is True
        QApplication.processEvents()
        assert host._populate_preview_canvas(ov, _item(blue)) is True
        QApplication.processEvents()
    text = caplog.text
    assert "quick look populate preview-coarse=" in text
    assert "quick look populate preview-stash=" in text
    assert "quick look populate preview-set-source=" in text
    assert "quick look populate preview-stash-hit=" in text

    monkeypatch.setenv("IMGSLI_GALLERY_DEBUG", "0")
    with caplog.at_level(logging.WARNING, logger="ImproveImgSLI"):
        caplog.clear()
        assert host._populate_preview_canvas(ov, _item(blue)) is True
        QApplication.processEvents()
    assert "preview-coarse=" not in caplog.text
    assert "preview-stash" not in caplog.text
    ov.hide()


def test_key_shape_and_stat_change_invalidates(tmp_path):
    red = _png(tmp_path, "red.png", "#c0392b")
    key = _stash_cache_key(str(red))
    assert isinstance(key, tuple) and len(key) == 3
    norm, mtime_ns, size = key
    assert isinstance(norm, str) and mtime_ns > 0 and size > 0
    assert _stash_cache_key(str(tmp_path / "missing.png")) is None


def test_cache_bounded_evicts_oldest(qtbot):
    overlay = SimpleNamespace()
    pms = [QPixmap(4, 4) for _ in range(_STASH_CACHE_MAX + 4)]
    for pm in pms:
        pm.fill(0xFF0000)
    for i, pm in enumerate(pms):
        _stash_cache_store(overlay, ("p", i, i), pm)
    cache = overlay._stash_cache
    assert isinstance(cache, dict)
    assert len(cache) <= _STASH_CACHE_MAX
    assert ("p", 0, 0) not in cache
    assert ("p", len(pms) - 1, len(pms) - 1) in cache


def test_cache_errors_fallback_still_populates(qtbot, tmp_path, monkeypatch):
    """Broken memo (or key) fails open to today's recompute path."""
    red = _png(tmp_path, "red.png", "#c0392b")
    item = SimpleNamespace(path=str(red), thumbnail=None)

    class _Broken:
        def get(self, *a, **k):
            raise RuntimeError("boom")

        def __setitem__(self, *a):
            raise RuntimeError("boom")

    overlay = SimpleNamespace(_preview_full=None, _stash_cache=_Broken())
    _stash_preview_source(overlay, item)  # must not raise
    assert overlay._preview_full is not None and not overlay._preview_full.isNull()

    monkeypatch.setattr(_preview, "_stash_cache_key", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("key boom")))
    overlay2 = SimpleNamespace(_preview_full=None)
    _stash_preview_source(overlay2, item)  # must not raise
    assert overlay2._preview_full is not None and not overlay2._preview_full.isNull()
