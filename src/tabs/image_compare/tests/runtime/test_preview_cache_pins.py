"""Displayed previews survive budget eviction and explicit evict.

Regression: preview-tier budget was unguarded FIFO and pins covered only
pixel keys, so a shown QImage could be evicted before tiles replaced it,
breaking the preview backing. Pinned (displayed) preview keys now survive
both paths; explicit evict() spares them until unpin (path switch).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage

from tabs.image_compare.pipeline.cache import PipelineCache


def _qimg():
    img = QImage(32, 32, QImage.Format.Format_RGBA8888)
    img.fill(0xFF334455)
    return img


def test_pinned_preview_survives_budget_eviction(tmp_path):
    cache = PipelineCache(max_preview=1)
    p1 = str(tmp_path / "a.png")
    p2 = str(tmp_path / "b.png")
    cache.put_preview(p1, None, _qimg())
    cache.set_pinned_paths([p1])
    cache.put_preview(p2, None, _qimg())
    assert cache.get_preview(p1, None) is not None
    assert cache.get_preview(p2, None) is None


def test_unpinned_preview_evicted_over_budget(tmp_path):
    cache = PipelineCache(max_preview=1)
    p1 = str(tmp_path / "a.png")
    p2 = str(tmp_path / "b.png")
    cache.put_preview(p1, None, _qimg())
    cache.put_preview(p2, None, _qimg())
    assert cache.get_preview(p1, None) is None
    assert cache.get_preview(p2, None) is not None


def test_evict_spares_pinned_preview_until_unpin(tmp_path):
    cache = PipelineCache()
    p1 = str(tmp_path / "a.png")
    cache.put_preview(p1, None, _qimg())
    cache.set_pinned_paths([p1])
    cache.evict(p1)
    assert cache.get_preview(p1, None) is not None
    cache.unpin_paths([p1])
    cache.evict(p1)
    assert cache.get_preview(p1, None) is None
