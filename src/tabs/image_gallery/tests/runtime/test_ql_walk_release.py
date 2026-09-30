"""QL walk release: navigating away must not drop memos (stash-hit rebuild).

Reproduces the production log — populate(A) -> release-for-walk ->
populate(B) -> release-for-walk -> populate(A): the last step performs ZERO
source decodes AND ZERO ``_store_from_pixmap`` materializations (the ~207ms
stash-hit rebuild), returns the SAME store object, both memos stay open, and
open fd/memmap-backed stores stay within the cache bound.

Ownership rule under test: walk keeps memos (bound caps fds), overlay-close
drops all, canvas closes only privately-built stores.
"""

from __future__ import annotations

from pathlib import Path

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
    made: list = []
    _real_coarse = PyramidPixelStore.coarse_from_source
    _real_pyr = _preview._pyramid_pixmap_for
    _real_reader = _preview._load_scaled_pixmap
    _real_mat = host._store_from_pixmap

    def _coarse(cls, *a, **k):
        counts["coarse"] += 1
        store = _real_coarse(*a, **k)
        made.append(store)
        return store

    def _pyr(*a, **k):
        counts["pyramid"] += 1
        return _real_pyr(*a, **k)

    def _reader(*a, **k):
        counts["reader"] += 1
        return _real_reader(*a, **k)

    def _mat(*a, **k):
        counts["materialize"] += 1
        made.append(_real_mat(*a, **k))
        return made[-1]

    monkeypatch.setattr(PyramidPixelStore, "coarse_from_source", classmethod(_coarse))
    monkeypatch.setattr(_preview, "_pyramid_pixmap_for", _pyr)
    monkeypatch.setattr(_preview, "_load_scaled_pixmap", _reader)
    monkeypatch.setattr(host, "_store_from_pixmap", _mat)
    return counts, made


def _open(store) -> bool:
    try:
        return bool(store.is_open)
    except Exception:
        return False


def test_walk_release_keeps_memos_zero_redecode(qtbot, tmp_path, monkeypatch):
    """A->walk->B->walk->A: last step free, same object, fds bounded."""
    red = _png(tmp_path, "red.png", "#c0392b")
    blue = _png(tmp_path, "blue.png", "#3a6ea5")
    counts, made = _counting_spies(monkeypatch)
    ov = _make_overlay(qtbot)
    fake = _FakeCanvas()
    monkeypatch.setattr(host, "_ensure_preview_canvas", lambda _ov: fake)

    assert host._populate_preview_canvas(ov, _item(red)) is True
    store_a = ov._preview_store
    assert store_a is not None and _open(store_a)
    QApplication.processEvents()

    # Walk away: the walk step — not the overlay release.
    ov._release_preview_resources(for_walk=True)
    QApplication.processEvents()
    assert _open(store_a), "walk must not close the memoized live store"
    assert host._preview_store_cache_lookup(
        ov, _preview._stash_cache_key(str(red))
    ) is store_a, "walk must keep the store memo"

    assert host._populate_preview_canvas(ov, _item(blue)) is True
    store_b = ov._preview_store
    assert store_b is not None and store_b is not store_a and _open(store_b)
    QApplication.processEvents()

    ov._release_preview_resources(for_walk=True)
    QApplication.processEvents()
    assert _open(store_a) and _open(store_b), "walk must keep every memo open"

    # Walk back: the production-log step — must be fully free.
    frozen = dict(counts)
    assert host._populate_preview_canvas(ov, _item(red)) is True
    QApplication.processEvents()

    assert counts == frozen, f"walk revisit must not decode or materialize, saw {counts}"
    assert ov._preview_store is store_a, "revisit must hand the SAME store object"
    assert _open(store_a) and _open(store_b)
    assert fake.sources[-1] is store_a

    # Both memo dicts survive the walk (pixmap stash + store cache).
    for p in (red, blue):
        key = _preview._stash_cache_key(str(p))
        assert _preview._stash_cache_lookup(ov, key) is not None, f"pixmap memo kept for {p}"
        assert host._preview_store_cache_lookup(ov, key) is not None, f"store memo kept for {p}"

    # fd/memmap hygiene: open stores never exceed the memo bound.
    bound = host._preview_store_cache_max()
    cache = getattr(ov, "_preview_store_cache", {})
    assert isinstance(cache, dict) and len(cache) <= bound
    open_stores = [s for s in made if s is not None and _open(s)]
    assert len(open_stores) <= bound, f"open stores bounded by {bound}, saw {len(open_stores)}"

    # Overlay close still drops everything (no leak past close).
    ov._release_preview_resources()
    QApplication.processEvents()
    assert ov._preview_store is None
    assert getattr(ov, "_preview_store_cache", {}) == {}
    for st in (store_a, store_b):
        assert not _open(st), "overlay release closes every memoized store"
    ov.hide()


def test_canvas_closes_only_privately_built_stores(qtbot, tmp_path):
    """Real canvas: memos survive set/clear, privates close, never twice."""
    from tabs.image_gallery.ui.quick_look.preview_canvas import QuickLookCanvasWidget

    red = _png(tmp_path, "red.png", "#c0392b")
    blue = _png(tmp_path, "blue.png", "#3a6ea5")
    memo = host._coarse_store_for(str(red))
    priv = host._coarse_store_for(str(blue))
    assert memo is not None and _open(memo)
    assert priv is not None and _open(priv)

    closes: list = []
    _real_close = priv.close

    def _counting_close(*a, **k):
        closes.append(1)
        return _real_close(*a, **k)

    priv.close = _counting_close  # type: ignore[method-assign]

    from types import SimpleNamespace

    ov = SimpleNamespace(_preview_store_cache={"k": memo}, _preview_store=None)
    card = QuickLookCanvasWidget(None)
    qtbot.addWidget(card)
    host._install_memo_probe(ov, card)

    # Privately-built held closes on replace.
    card.set_source(priv)
    assert card._store is priv
    card.set_source(memo)
    assert closes == [1], "replaced private store closes exactly once"
    assert not _open(priv) and _open(memo)

    # Memoized held survives clear + replace (cache owns it).
    card.clear_source()
    assert card._store is None and _open(memo), "clear must not close the memo"
    card.set_source(memo)
    priv2 = host._coarse_store_for(str(blue))
    assert priv2 is not None and _open(priv2)
    card.set_source(priv2)
    assert _open(memo), "replace must not close the memoized held store"
    assert card._store is priv2

    # Already-closed held never double-closes.
    card.clear_source()
    assert closes == [1], "first private already closed once"
    card._store = priv  # re-hold a closed store; clear must not close again.
    card.clear_source()
    assert closes == [1], "closed held store must never close twice"

    for st in (memo, priv2):
        try:
            st.close()
        except Exception:
            pass
