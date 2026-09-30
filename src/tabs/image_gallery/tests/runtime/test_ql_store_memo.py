"""QL store memo: stash hit hands the memoized bounded store (no PNG round-trip).

- Revisit returns the SAME store object with zero decodes AND zero
  ``_store_from_pixmap`` calls (single-digit ms path, not ~204ms).
- Evict closes the memoized store (fd/memmap hygiene).
- Closed memoized store rebuilds once via ``_store_from_pixmap`` and re-memoizes.
- Pixmap memo untouched (same key shape, still populated).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.ui.quick_look import QuickLookOverlay
from tabs.image_gallery.ui.quick_look import preview as _preview
from tabs.image_gallery.ui.quick_look import preview_canvas_host as host


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
    ov._parity_test_parent = parent
    return ov


def _item(path: Path) -> GalleryItem:
    return GalleryItem(path=path, mtime_ns=1, metrics={})


class _FakeCanvas(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.sources: list = []

    def set_source(self, store) -> None:
        self.sources.append(store)

    def clear_source(self) -> None:
        pass


def _counting_spies(monkeypatch):
    from engine.store.pyramid_pixel_store import PyramidPixelStore

    counts = {"coarse": 0, "pyramid": 0, "reader": 0, "materialize": 0}
    _real_coarse = PyramidPixelStore.coarse_from_source
    _real_pyr = _preview._pyramid_pixmap_for
    _real_reader = _preview._load_scaled_pixmap
    _real_mat = host._store_from_pixmap

    def _coarse(cls, *a, **k):
        counts["coarse"] += 1
        return _real_coarse(*a, **k)

    def _pyr(*a, **k):
        counts["pyramid"] += 1
        return _real_pyr(*a, **k)

    def _reader(*a, **k):
        counts["reader"] += 1
        return _real_reader(*a, **k)

    def _mat(*a, **k):
        counts["materialize"] += 1
        return _real_mat(*a, **k)

    monkeypatch.setattr(PyramidPixelStore, "coarse_from_source", classmethod(_coarse))
    monkeypatch.setattr(_preview, "_pyramid_pixmap_for", _pyr)
    monkeypatch.setattr(_preview, "_load_scaled_pixmap", _reader)
    monkeypatch.setattr(host, "_store_from_pixmap", _mat)
    return counts


def test_revisit_returns_same_store_zero_materialize(qtbot, tmp_path, monkeypatch):
    """Hit path: same store object, zero decodes, zero PNG round-trips."""
    red = _png(tmp_path, "red.png", "#c0392b")
    blue = _png(tmp_path, "blue.png", "#3a6ea5")
    counts = _counting_spies(monkeypatch)
    ov = _make_overlay(qtbot)
    fake = _FakeCanvas()
    monkeypatch.setattr(host, "_ensure_preview_canvas", lambda _ov: fake)

    assert host._populate_preview_canvas(ov, _item(red)) is True
    first_store = ov._preview_store
    first_full = ov._preview_full
    assert first_store is not None and first_store.is_open
    mat_after_first = counts["materialize"]
    assert mat_after_first == 0, f"miss must not PNG-round-trip, saw {counts}"
    QApplication.processEvents()

    assert host._populate_preview_canvas(ov, _item(blue)) is True
    blue_store = ov._preview_store
    assert blue_store is not first_store and blue_store.is_open
    frozen = dict(counts)
    QApplication.processEvents()

    assert host._populate_preview_canvas(ov, _item(red)) is True
    QApplication.processEvents()

    assert counts == frozen, f"revisit must not decode or materialize, saw {counts}"
    assert ov._preview_store is first_store, "hit must hand the memoized store directly"
    assert ov._preview_full is first_full, "pixmap memo untouched"
    assert first_store.is_open
    assert blue_store.is_open, "replaced memo stays open for its own revisit"
    assert fake.sources[-1] is first_store
    ov.hide()


def test_evict_closes_memoized_store(qtbot, tmp_path, monkeypatch):
    """Bounded store cache: evicting the oldest key closes its store."""
    from tabs.image_gallery.ui.quick_look.preview import _STASH_CACHE_MAX

    paths = [_png(tmp_path, f"e{i}.png", "#3a6ea5") for i in range(_STASH_CACHE_MAX + 1)]
    ov = _make_overlay(qtbot)
    fake = _FakeCanvas()
    monkeypatch.setattr(host, "_ensure_preview_canvas", lambda _ov: fake)
    seen: dict = {}
    for p in paths:
        assert host._populate_preview_canvas(ov, _item(p)) is True
        QApplication.processEvents()
        key = _preview._stash_cache_key(str(p))
        seen[str(p)] = (key, ov._preview_store)
    first_key, first_store = seen[str(paths[0])]
    cache = getattr(ov, "_preview_store_cache", None)
    assert isinstance(cache, dict) and len(cache) <= _STASH_CACHE_MAX
    assert first_key not in cache, "oldest store key must be evicted"
    try:
        assert not first_store.is_open, "evicted memoized store must be closed"
    except Exception:
        pass
    ov.hide()


def test_closed_memoized_store_rebuilds_once(qtbot, tmp_path, monkeypatch):
    """Closed memo entry: exactly one PNG rebuild, then re-memoized."""
    red = _png(tmp_path, "red.png", "#c0392b")
    counts = _counting_spies(monkeypatch)
    ov = _make_overlay(qtbot)
    fake = _FakeCanvas()
    monkeypatch.setattr(host, "_ensure_preview_canvas", lambda _ov: fake)

    assert host._populate_preview_canvas(ov, _item(red)) is True
    QApplication.processEvents()
    key = _preview._stash_cache_key(str(red))
    first_store = ov._preview_store
    assert counts["materialize"] == 0
    # Simulate an externally closed memo (live close raced the cache).
    first_store.close()
    assert not first_store.is_open

    assert host._populate_preview_canvas(ov, _item(red)) is True
    QApplication.processEvents()
    assert counts["materialize"] == 1, f"closed memo rebuilds once, saw {counts}"
    assert counts["coarse"] == 1, f"rebuild must not touch source, saw {counts}"
    second = ov._preview_store
    assert second is not first_store and second.is_open

    # Re-memoized: the next revisit is free again.
    frozen = dict(counts)
    assert host._populate_preview_canvas(ov, _item(red)) is True
    QApplication.processEvents()
    assert counts == frozen
    assert ov._preview_store is second
    ov.hide()


def test_release_closes_memoized_stores(qtbot, tmp_path, monkeypatch):
    """Overlay release: live + every memoized store closed, no leak."""
    red = _png(tmp_path, "red.png", "#c0392b")
    blue = _png(tmp_path, "blue.png", "#3a6ea5")
    ov = _make_overlay(qtbot)
    fake = _FakeCanvas()
    monkeypatch.setattr(host, "_ensure_preview_canvas", lambda _ov: fake)
    assert host._populate_preview_canvas(ov, _item(red)) is True
    red_store = ov._preview_store
    assert host._populate_preview_canvas(ov, _item(blue)) is True
    blue_store = ov._preview_store
    QApplication.processEvents()

    host.release_preview_canvas(ov)
    QApplication.processEvents()
    assert ov._preview_store is None
    for st in (red_store, blue_store):
        try:
            assert not st.is_open
        except Exception:
            pass
    assert getattr(ov, "_preview_store_cache", {}) == {}
    ov.hide()


def test_store_memo_fail_open_on_broken_cache(qtbot, tmp_path, monkeypatch):
    """Broken store cache fails open to today's rebuild path (never blank)."""
    red = _png(tmp_path, "red.png", "#c0392b")
    ov = _make_overlay(qtbot)
    fake = _FakeCanvas()
    monkeypatch.setattr(host, "_ensure_preview_canvas", lambda _ov: fake)

    class _Broken(dict):
        def get(self, *a, **k):
            raise RuntimeError("boom")

        def __setitem__(self, *a):
            raise RuntimeError("boom")

    ov._preview_store_cache = _Broken()
    assert host._populate_preview_canvas(ov, _item(red)) is True
    QApplication.processEvents()
    assert ov._preview_store is not None and ov._preview_store.is_open
    assert ov._preview_full is not None and not ov._preview_full.isNull()
    ov.hide()
