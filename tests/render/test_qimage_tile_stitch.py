"""qimage_from_pixel_source must not call materialize_full for whole stores."""

import numpy as np
from PIL import Image

from engine.store.tiled_pixel_store import (
    TiledPixelStore,
    qimage_from_pixel_source,
)


def _gradient_rgba(w: int, h: int) -> Image.Image:
    """Per-pixel distinct content so a tile-order/placement bug changes pixels.

    A uniform fill would pass every assertion below regardless of stitch order
    (the false-confidence case); a gradient makes the stitched output falsifiable.
    """
    xs = (np.arange(w, dtype=np.int32) * 255 // max(w - 1, 1)).astype(np.uint8)
    ys = (np.arange(h, dtype=np.int32) * 255 // max(h - 1, 1)).astype(np.uint8)
    r = np.tile(xs, (h, 1))
    g = np.tile(ys[:, None], (1, w))
    b = ((r.astype(np.int32) + g.astype(np.int32)) % 256).astype(np.uint8)
    a = np.full((h, w), 255, np.uint8)
    return Image.fromarray(np.stack([r, g, b, a], axis=-1), "RGBA")


def test_whole_store_qimage_uses_tile_stitch(monkeypatch):
    img = _gradient_rgba(1024, 768)
    store = TiledPixelStore.from_pil(img)
    calls: list[str] = []

    def _spy_materialize_full():
        calls.append("materialize_full")
        raise AssertionError("materialize_full must not run")

    monkeypatch.setattr(store, "materialize_full", _spy_materialize_full)

    qimage = qimage_from_pixel_source(store)
    assert not qimage.isNull()
    assert qimage.width() == 1024
    assert qimage.height() == 768
    assert calls == []

    # Content identity across the whole canvas: every sampled pixel (incl. points
    # in different tiles and the far corner) equals the source's own pixel. A
    # wrong tile order/offset would surface as a mismatch here.
    for x, y in ((0, 0), (100, 700), (511, 383), (512, 384), (900, 50), (1023, 767)):
        assert qimage.pixelColor(x, y).getRgb() == img.getpixel((x, y)), (x, y)

    store.close()
