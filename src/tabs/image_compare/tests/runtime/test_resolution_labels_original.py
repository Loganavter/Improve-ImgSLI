"""HUD resolution chips show each file's ORIGINAL dims via header probe.

Regression (W4): after unify replaces ``image_state`` with the max-canvas
pair, the InfoHUD chips must still show each file's original dims from
first paint. ``get_image_dimensions`` tries the file-header probe first
(no full decode) and falls through to the existing image_state → pipeline
chain on ANY probe failure.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import numpy as np
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_compare.use_cases import chrome_sync
from tabs.image_compare.use_cases.chrome_sync import get_image_dimensions


class _Img:
    """Minimal QImage-like stub (callable width/height, not null, open)."""

    def __init__(self, w: int, h: int):
        self._w = w
        self._h = h

    def isNull(self):  # noqa: N802 - Qt naming
        return False

    def width(self):
        return self._w

    def height(self):
        return self._h


def _write_png(path: str, width: int, height: int) -> None:
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    arr[:, :, :3] = 128
    arr[:, :, 3] = 255
    Image.fromarray(arr, mode="RGBA").save(path, format="PNG")


def _store(doc, img1, img2):
    viewport = SimpleNamespace(
        session_data=SimpleNamespace(
            image_state=SimpleNamespace(image1=img1, image2=img2)
        )
    )

    def _slot(name: str):
        if name == "document":
            return doc
        return None

    return SimpleNamespace(viewport=viewport, get_session_state_slot=_slot)


def test_file_dims_win_over_unified_image_state(tmp_path):
    chrome_sync._original_dims_cache.clear()
    p1 = str(tmp_path / "a.png")
    p2 = str(tmp_path / "b.png")
    _write_png(p1, 64, 48)
    _write_png(p2, 32, 24)
    # image_state holds the UNIFIED max-canvas pair (as after unify).
    doc = SimpleNamespace(image1_path=p1, image2_path=p2)
    store = _store(doc, _Img(200, 200), _Img(200, 200))
    assert get_image_dimensions(store, 1) == (64, 48)
    assert get_image_dimensions(store, 2) == (32, 24)


def test_deleted_file_falls_back_to_existing_chain(tmp_path):
    chrome_sync._original_dims_cache.clear()
    p1 = str(tmp_path / "gone.png")
    _write_png(p1, 64, 48)
    doc = SimpleNamespace(image1_path=p1, image2_path=None)
    store = _store(doc, _Img(200, 200), None)
    assert get_image_dimensions(store, 1) == (64, 48)
    # File deleted after caching: probe fails → existing chain, no crash.
    os.unlink(p1)
    chrome_sync._original_dims_cache.clear()
    assert get_image_dimensions(store, 1) == (200, 200)
