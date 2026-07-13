"""docs/dev/rendering/tile-rendering-system.md Phase 3: the memmap-backed
LazyPixelSource used to keep very large source images from staying
resident as a full-size Python-owned PIL buffer for the document's
lifetime."""

import numpy as np
from PIL import Image

from core.constants import AppConstants
from shared.image_processing.lazy_pixel_source import (
    LazyPixelSource,
    close_if_lazy,
    maybe_wrap_for_lazy_storage,
)
from shared.rendering.image_identity import image_uid


def _gradient_image(width=64, height=48):
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    arr[:, :, 0] = np.arange(width, dtype=np.uint8)[None, :]
    arr[:, :, 1] = np.arange(height, dtype=np.uint8)[:, None]
    arr[:, :, 2] = 128
    arr[:, :, 3] = 255
    return Image.fromarray(arr, mode="RGBA")


def test_crop_matches_direct_pil_crop():
    original = _gradient_image()
    source = LazyPixelSource.from_pil(original)
    box = (10, 5, 40, 30)

    cropped = source.crop(box)
    expected = original.crop(box)

    assert cropped.size == expected.size
    assert list(cropped.getdata()) == list(expected.getdata())
    source.close()


def test_to_pil_round_trip():
    original = _gradient_image()
    source = LazyPixelSource.from_pil(original)

    restored = source.to_pil()

    assert restored.size == original.size
    assert list(restored.getdata()) == list(original.getdata())
    source.close()


def test_size_width_height_properties():
    original = _gradient_image(width=100, height=64)
    source = LazyPixelSource.from_pil(original)

    assert source.size == (100, 64)
    assert source.width == 100
    assert source.height == 64
    source.close()


def test_image_uid_works_on_lazy_source():
    source = LazyPixelSource.from_pil(_gradient_image())

    uid_first = image_uid(source)
    uid_second = image_uid(source)

    assert uid_first == uid_second
    assert uid_first != 0
    source.close()


def test_maybe_wrap_leaves_small_images_untouched():
    small = _gradient_image(width=32, height=32)

    result = maybe_wrap_for_lazy_storage(small)

    assert result is small


def test_maybe_wrap_spills_images_past_threshold():
    threshold = AppConstants.PHASE3_LAZY_THRESHOLD_PX
    big = Image.new("RGBA", (threshold + 1, 8), (1, 2, 3, 4))

    result = maybe_wrap_for_lazy_storage(big)

    assert isinstance(result, LazyPixelSource)
    assert result.size == (threshold + 1, 8)
    close_if_lazy(result)


def test_maybe_wrap_none_is_noop():
    assert maybe_wrap_for_lazy_storage(None) is None


def test_close_if_lazy_noop_for_plain_pil():
    plain = _gradient_image()
    close_if_lazy(plain)  # must not raise
    assert plain.size == (64, 48)


def test_close_removes_backing_file():
    source = LazyPixelSource.from_pil(_gradient_image())
    path = source._path

    source.close()

    import os

    assert not os.path.exists(path)
