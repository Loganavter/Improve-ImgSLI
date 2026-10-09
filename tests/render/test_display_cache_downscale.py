"""Display cache downscale must not materialize full TiledPixelStore."""

from unittest.mock import patch

from PIL import Image

from engine.store.tiled_pixel_store import TiledPixelStore


def test_downscale_pair_to_limit_never_materializes_full():
    store1 = TiledPixelStore.from_pil(Image.new("RGBA", (4096, 2048), "red"))
    store2 = TiledPixelStore.from_pil(Image.new("RGBA", (4096, 2048), "blue"))

    with patch.object(TiledPixelStore, "materialize_full") as materialize:
        from engine.store.pixel_ops.downscale import downscale_pair_to_limit

        d1, d2 = downscale_pair_to_limit(store1, store2, 1024)
        materialize.assert_not_called()

    assert max(d1.size) <= 1024
    assert max(d2.size) <= 1024
    # Content identity: the two stores must not be swapped or mixed. A uniform
    # size-only check would pass even if d1 held store2's pixels.
    assert d1.convert("RGB").getpixel((d1.size[0] // 2, d1.size[1] // 2)) == (255, 0, 0)
    assert d2.convert("RGB").getpixel((d2.size[0] // 2, d2.size[1] // 2)) == (0, 0, 255)
    store1.close()
    store2.close()