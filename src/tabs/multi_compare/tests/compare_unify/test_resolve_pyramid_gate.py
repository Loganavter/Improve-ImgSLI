"""MC resolve holds preview until the pixel tier's pyramid completes.

Regression for the early-replace seen in the 2026-09-30 log: full noted at
trace seq 73 while its pyramid built frames later, so the raw store replaced
the preview before any tile was resident. IC parity (pick_display_image):
pixel tier wins only when pyramid-gated ready.
"""

from __future__ import annotations

import pytest

from engine.store.tiled_pixel_store import TiledPixelStore
from tabs.multi_compare.pipeline import cache as mc_cache

class _Store(TiledPixelStore):
    """TiledPixelStore identity without a real memmap (never opened)."""

    def __init__(self) -> None:
        pass


class _Pyramid:
    def __init__(self, complete: bool) -> None:
        self._complete = complete

    def is_complete(self) -> bool:
        return self._complete


def _preview():
    from PySide6.QtGui import QImage

    img = QImage(64, 48, QImage.Format.Format_RGBA8888)
    img.fill(0xFF808080)
    assert not img.isNull()
    return img


def _cache_with(store, preview, monkeypatch, *, pyramid=None):
    from pathlib import Path

    c = mc_cache.MultiComparePixelCache()
    path = str(Path("/tmp/mc-gate-probe.png"))
    c.put_pixel(path, store)
    if preview is not None:
        c.put_preview(path, preview)
    monkeypatch.setattr(mc_cache, "pyramid_for", lambda _s: pyramid, raising=False)
    # _pyramid_ready imports pyramid_for lazily; patch the source module too.
    import engine.store.pyramid_registry as _reg

    monkeypatch.setattr(_reg, "pyramid_for", lambda _s: pyramid, raising=False)
    return c, path


def test_incomplete_pyramid_holds_preview(monkeypatch):
    c, path = _cache_with(_Store(), _preview(), monkeypatch, pyramid=_Pyramid(False))
    assert c.resolve(path) is not None
    assert c.resolve(path) == c.get_preview(path)


def test_complete_pyramid_returns_store(monkeypatch):
    c, path = _cache_with(_Store(), _preview(), monkeypatch, pyramid=_Pyramid(True))
    assert c.resolve(path) is c.get_pixel(path)


def test_no_preview_fail_open_returns_store(monkeypatch):
    c, path = _cache_with(_Store(), None, monkeypatch, pyramid=_Pyramid(False))
    assert c.resolve(path) is c.get_pixel(path)


def test_untracked_store_holds_preview(monkeypatch):
    c, path = _cache_with(_Store(), _preview(), monkeypatch, pyramid=None)
    assert c.resolve(path) == c.get_preview(path)


def test_non_store_pixel_unchanged(monkeypatch):
    c, path = _cache_with(object(), _preview(), monkeypatch, pyramid=_Pyramid(False))
    assert c.resolve(path) is c.get_pixel(path)
