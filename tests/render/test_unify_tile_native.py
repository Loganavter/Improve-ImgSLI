"""Tile-native unify vs PIL reference."""

from PIL import Image

from shared.image_processing.pixel_ops.unify import unify_pair
from shared.image_processing.resize import resize_images_processor
from shared.image_processing.tiled_pixel_store import TiledPixelStore


def _gradient(w, h):
    img = Image.new("RGBA", (w, h))
    for y in range(h):
        for x in range(w):
            img.putpixel((x, y), (x % 256, y % 256, 128, 255))
    return img


def test_unify_pair_matches_pil_reference():
    img1 = _gradient(640, 480)
    img2 = _gradient(512, 400)
    s1 = TiledPixelStore.from_pil(img1)
    s2 = TiledPixelStore.from_pil(img2)

    ref1, ref2 = resize_images_processor(img1.copy(), img2.copy())
    out1, out2 = unify_pair(s1, s2)

    assert out1 is not None and out2 is not None
    assert out1.size == ref1.size == ref2.size

    got1 = out1.crop((0, 0, out1.width, out1.height)) if isinstance(out1, TiledPixelStore) else out1
    got2 = out2.crop((0, 0, out2.width, out2.height)) if isinstance(out2, TiledPixelStore) else out2

    for ref, got in ((ref1, got1), (ref2, got2)):
        for y in range(10, ref.height - 10, 37):
            for x in range(10, ref.width - 10, 41):
                assert ref.getpixel((x, y)) == got.getpixel((x, y))

    if isinstance(out1, TiledPixelStore):
        out1.close()
    if isinstance(out2, TiledPixelStore):
        out2.close()
    s1.close()
    s2.close()
