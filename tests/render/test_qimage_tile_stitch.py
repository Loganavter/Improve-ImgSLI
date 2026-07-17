"""qimage_from_pixel_source must not call materialize_full for whole stores."""

from PIL import Image

from shared.image_processing.tiled_pixel_store import (
    TiledPixelStore,
    qimage_from_pixel_source,
)


def test_whole_store_qimage_uses_tile_stitch(monkeypatch):
    img = Image.new("RGBA", (1024, 768), (10, 20, 30, 255))
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

    store.close()
