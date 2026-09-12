"""Large slot images load into TiledPixelStore without a full numpy resident."""

from PIL import Image

from shared.image_processing.tiled_pixel_store import TiledPixelStore
from tabs.multi_compare.tests.pixel_fixtures import slot_image


def test_read_image_returns_tiled_pixel_store(tmp_path):
    path = tmp_path / "big.png"
    Image.new("RGBA", (800, 600), (10, 20, 30, 255)).save(path)

    store = TiledPixelStore.from_path(path)

    assert isinstance(store, TiledPixelStore)
    assert store.size == (800, 600)
    store.close()


def test_compare_slot_image_is_not_numpy():
    store = slot_image(64, 48)
    try:
        assert not hasattr(store, "shape")
        assert store.width == 64
        assert store.height == 48
    finally:
        store.close()
