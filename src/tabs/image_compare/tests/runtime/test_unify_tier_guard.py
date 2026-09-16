"""Unify never consumes preview-tier QImages.

Regression: the unify worker peeked pixel-then-preview per slot, so a
(QImage preview, full-res store) pair reached ``unify_pair``, which
silently upscaled 1024px into a full-size store (full resample cost) and
poisoned the unify memo as a full-res pair. The entry guard skips any
pair with a QImage side; the full-res arrival re-triggers unify.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage

from engine.store.pixel_ops.unify import unify_pair
from engine.store.tiled_pixel_store import TiledPixelStore


def _tiny_store():
    return TiledPixelStore.allocate(64, 48)


def test_unify_skips_preview_qimage_side():
    store = _tiny_store()
    try:
        preview = QImage(64, 48, QImage.Format.Format_RGBA8888)
        assert unify_pair(preview, store) == (None, None)
        assert unify_pair(store, preview) == (None, None)
        assert unify_pair(preview, preview) == (None, None)
    finally:
        store.close()


def test_unify_empty_and_same_size_passthrough_unchanged():
    assert unify_pair(None, None) == (None, None)
    owned = [_tiny_store(), _tiny_store()]
    try:
        out1, out2 = unify_pair(owned[0], owned[1], "LANCZOS")
        # small same-size pair: PIL path returns equivalent stores
        assert out1 is not None and out2 is not None
        assert (out1.width, out1.height) == (64, 48)
        assert (out2.width, out2.height) == (64, 48)
        owned.extend([s for s in (out1, out2) if s not in owned])
    finally:
        for s in owned:
            try:
                s.close()
            except Exception:
                pass
