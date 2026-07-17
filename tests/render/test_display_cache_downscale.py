"""Display cache downscale must not materialize full TiledPixelStore."""

from unittest.mock import patch

from PIL import Image

from shared.image_processing.tiled_pixel_store import TiledPixelStore


def test_downscale_pair_to_limit_never_materializes_full():
    store1 = TiledPixelStore.from_pil(Image.new("RGBA", (4096, 2048), "red"))
    store2 = TiledPixelStore.from_pil(Image.new("RGBA", (4096, 2048), "blue"))

    with patch.object(TiledPixelStore, "materialize_full") as materialize:
        from shared.image_processing.pixel_ops.downscale import downscale_pair_to_limit

        d1, d2 = downscale_pair_to_limit(store1, store2, 1024)
        materialize.assert_not_called()

    assert max(d1.size) <= 1024
    assert max(d2.size) <= 1024
    store1.close()
    store2.close()
