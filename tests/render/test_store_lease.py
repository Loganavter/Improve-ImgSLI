"""StoreLease generation invalidation tests."""

from PIL import Image

from shared.image_processing.store_lease import StoreLease
from shared.image_processing.tiled_pixel_store import TiledPixelStore


def test_lease_invalid_after_close():
    store = TiledPixelStore.from_pil(Image.new("RGBA", (32, 32), "red"))
    lease = StoreLease.capture(store)
    assert lease is not None
    assert lease.valid

    generation = store.generation
    store.close()

    assert not lease.valid
    assert store.generation == generation + 1
    assert lease.restore() is None


def test_worker_skips_stale_lease():
    store = TiledPixelStore.from_pil(Image.new("RGBA", (16, 16), "blue"))
    lease = StoreLease.capture(store)
    store.close()

    from shared.image_processing.pixel_ops.unify import unify_pair

    img = Image.new("RGBA", (16, 16), "green")
    u1, u2 = unify_pair(store, img, lease1=lease, lease2=None)
    assert u1 is None and u2 is None
