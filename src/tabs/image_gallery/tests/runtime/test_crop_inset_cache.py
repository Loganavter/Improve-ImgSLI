"""Sharpness-crop inset memo: populate_crop caches the final pixmap.

Same (path, stat, scale) twice → single decode; path/scale change →
recompute; any cache error fails open to today's recompute path.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from PySide6.QtGui import QPixmap

from tabs.image_gallery.ui.quick_look import insets as _insets
from tabs.image_gallery.ui.quick_look.insets import (
    _CROP_CACHE_MAX,
    _crop_cache_key,
    _crop_cache_store,
    populate_crop,
)


def _solid(path: Path, rgb: tuple[int, int, int], size=(640, 480)) -> Path:
    Image.new("RGB", size, rgb).save(path, "PNG")
    return path


class _Pix:
    def __init__(self) -> None:
        self.pixmap = None
        self.text = None
        self.calls = 0

    def update_region(self, name, pixmap=None, text=None):
        self.calls += 1
        self.pixmap = pixmap
        self.text = text


class _Host:
    def __init__(self) -> None:
        self.visible = None

    def setVisible(self, visible):
        self.visible = visible


def _overlay():
    return SimpleNamespace(_crop_host=_Host(), _crop_pix=_Pix(), _preview_full=None)


def _counting_spies(monkeypatch):
    """Wrap decode/copy helpers with counters; return counts dict."""
    counts = {"pyramid": 0, "reader": 0}
    _real_pyr = _insets._pyramid_pixmap_for
    _real_reader = _insets._load_scaled_pixmap

    def _pyr(*a, **k):
        counts["pyramid"] += 1
        return _real_pyr(*a, **k)

    def _reader(*a, **k):
        counts["reader"] += 1
        return _real_reader(*a, **k)

    monkeypatch.setattr(_insets, "_pyramid_pixmap_for", _pyr)
    monkeypatch.setattr(_insets, "_load_scaled_pixmap", _reader)
    return counts


def _decodes(counts) -> int:
    return counts["pyramid"] + counts["reader"]


def test_same_item_twice_single_decode(qtbot, tmp_path, monkeypatch):
    red = _solid(tmp_path / "red.png", (255, 0, 0))
    counts = _counting_spies(monkeypatch)
    overlay = _overlay()
    item = SimpleNamespace(path=str(red), thumbnail=None)

    populate_crop(overlay, item)
    assert overlay._crop_pix.pixmap is not None and not overlay._crop_pix.pixmap.isNull()
    first_pixmap = overlay._crop_pix.pixmap
    after_first = _decodes(counts)
    assert after_first > 0

    populate_crop(overlay, item)
    assert overlay._crop_pix.pixmap is not None and not overlay._crop_pix.pixmap.isNull()
    # Hit path: no further decode/copy work, same cached pixmap object.
    assert _decodes(counts) == after_first
    assert overlay._crop_pix.pixmap is first_pixmap


def test_different_path_recomputes(qtbot, tmp_path, monkeypatch):
    red = _solid(tmp_path / "red.png", (255, 0, 0))
    blue = _solid(tmp_path / "blue.png", (0, 0, 255))
    counts = _counting_spies(monkeypatch)
    overlay = _overlay()

    populate_crop(overlay, SimpleNamespace(path=str(red), thumbnail=None))
    assert overlay._crop_pix.pixmap is not None
    after_red = _decodes(counts)

    populate_crop(overlay, SimpleNamespace(path=str(blue), thumbnail=None))
    assert overlay._crop_pix.pixmap is not None
    assert _decodes(counts) > after_red


def test_different_scale_recomputes(qtbot, tmp_path, monkeypatch):
    red = _solid(tmp_path / "red.png", (255, 0, 0))
    counts = _counting_spies(monkeypatch)
    overlay = _overlay()
    item = SimpleNamespace(path=str(red), thumbnail=None)

    populate_crop(overlay, item)
    after_first = _decodes(counts)

    import sli_ui_toolkit.managers as _mgrs

    _real_scaled = _mgrs.scaled_px
    monkeypatch.setattr(_mgrs, "scaled_px", lambda v, _r=_real_scaled: _r(v) * 2 + 1)
    populate_crop(overlay, item)
    assert overlay._crop_pix.pixmap is not None
    assert _decodes(counts) > after_first


def test_cache_errors_fallback_still_populates(qtbot, tmp_path, monkeypatch):
    red = _solid(tmp_path / "red.png", (255, 0, 0))
    item = SimpleNamespace(path=str(red), thumbnail=None)

    # Corrupt per-overlay cache (raises on access) → recompute path.
    class _Broken:
        def get(self, *a, **k):
            raise RuntimeError("boom")

        def __setitem__(self, *a):
            raise RuntimeError("boom")

    overlay = _overlay()
    overlay._crop_cache = _Broken()
    populate_crop(overlay, item)  # must not raise
    assert overlay._crop_pix.pixmap is not None and not overlay._crop_pix.pixmap.isNull()

    # Key helper raising → fail-open recompute.
    monkeypatch.setattr(_insets, "_crop_cache_key", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("key boom")))
    overlay2 = _overlay()
    populate_crop(overlay2, item)  # must not raise
    assert overlay2._crop_pix.pixmap is not None and not overlay2._crop_pix.pixmap.isNull()


def test_cache_bounded_evicts_oldest(qtbot):
    overlay = _overlay()
    pms = [QPixmap(4, 4) for _ in range(_CROP_CACHE_MAX + 4)]
    for pm in pms:
        pm.fill(0xFF0000)
    for i, pm in enumerate(pms):
        _crop_cache_store(overlay, ("p", i, i, 150, 84), pm)
    cache = overlay._crop_cache
    assert isinstance(cache, dict)
    assert len(cache) <= _CROP_CACHE_MAX
    # Oldest evicted, newest retained.
    assert ("p", 0, 0, 150, 84) not in cache
    assert ("p", len(pms) - 1, len(pms) - 1, 150, 84) in cache


def test_key_shape_and_stat_change_invalidates(tmp_path):
    red = _solid(tmp_path / "red.png", (255, 0, 0))
    key = _crop_cache_key(str(red), 150, 84)
    assert isinstance(key, tuple) and len(key) == 5
    norm, mtime_ns, size, sw, sh = key
    assert isinstance(norm, str) and mtime_ns > 0 and size > 0
    assert (sw, sh) == (150, 84)
    # Missing path → None (fail-open, never raises).
    assert _crop_cache_key(str(tmp_path / "missing.png"), 150, 84) is None
