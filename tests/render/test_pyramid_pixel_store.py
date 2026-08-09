import numpy as np
from PIL import Image

from shared.image_processing.pyramid_pixel_store import (
    COARSEST_MIN_DIM,
    PyramidPixelStore,
    _halve_box_filter,
)
from shared.image_processing.tiled_pixel_store import TiledPixelStore


def _noise_store(width, height, seed=7):
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, size=(height, width, 4), dtype=np.uint8)
    arr[:, :, 3] = 255
    return TiledPixelStore.from_pil(Image.fromarray(arr, mode="RGBA")), arr


def test_halve_box_filter_even():
    arr = np.arange(4 * 4 * 4, dtype=np.uint8).reshape(4, 4, 4)
    out = _halve_box_filter(arr)
    assert out.shape == (2, 2, 4)
    expected = (
        arr.astype(np.uint16)[0::2, 0::2]
        + arr.astype(np.uint16)[1::2, 0::2]
        + arr.astype(np.uint16)[0::2, 1::2]
        + arr.astype(np.uint16)[1::2, 1::2]
        + 2
    ) >> 2
    assert np.array_equal(out, expected.astype(np.uint8))


def test_halve_box_filter_odd_dims_edge_padded():
    arr = np.full((3, 5, 4), 100, dtype=np.uint8)
    out = _halve_box_filter(arr)
    assert out.shape == (2, 3, 4)
    assert np.all(out == 100)


def test_build_levels_until_coarsest():
    store, _ = _noise_store(4096, 2048)
    pyramid = PyramidPixelStore.build_from(store)
    # 4096x2048 -> 2048x1024: min dim already <= COARSEST_MIN_DIM after one level.
    assert pyramid.level_count == 2
    assert pyramid.level(1).size == (2048, 1024)
    assert pyramid.is_complete()
    assert min(pyramid.level(pyramid.level_count - 1).size) <= COARSEST_MIN_DIM
    pyramid.close()
    assert pyramid.level_count == 1
    assert store.is_open
    store.close()


def test_ceil_halving_odd_dimensions():
    store, _ = _noise_store(2049, 1035)
    pyramid = PyramidPixelStore.build_from(store)
    assert pyramid.level(1).size == (1025, 518)
    pyramid.close()
    store.close()


def test_level_pixels_match_reference_downscale():
    store, arr = _noise_store(1030, 1029)
    pyramid = PyramidPixelStore.build_from(store)
    assert pyramid.level_count == 2
    level1 = np.asarray(pyramid.level(1).crop((0, 0, 515, 515)))
    assert np.array_equal(level1, _halve_box_filter(arr))
    pyramid.close()
    store.close()


def test_strip_seams_do_not_corrupt_output():
    # Height above build strip size forces multiple strips.
    store, arr = _noise_store(2048, 3000)
    pyramid = PyramidPixelStore(store)
    assert pyramid.build_next_level()
    level1 = np.asarray(pyramid.level(1).crop((0, 0, 1024, 1500)))
    assert np.array_equal(level1, _halve_box_filter(arr))
    pyramid.close()
    store.close()


def test_abort_discards_partial_level():
    store, _ = _noise_store(2048, 2048)
    pyramid = PyramidPixelStore(store)
    assert pyramid.build_next_level(should_abort=lambda: True) is False
    assert pyramid.level_count == 1
    store.close()


def test_closed_base_invalidates_build():
    store, _ = _noise_store(2048, 2048)
    pyramid = PyramidPixelStore(store)
    store.close()
    assert not pyramid.valid
    assert pyramid.build_next_level() is False
    assert pyramid.level_count == 1


def test_best_level_for_scale_clamps_to_built_levels():
    store, _ = _noise_store(4096, 4096)
    pyramid = PyramidPixelStore(store)
    assert pyramid.best_level_for_scale(0.01) == 0
    pyramid.build_all()
    assert pyramid.level_count == 3
    assert pyramid.best_level_for_scale(0.01) == 2
    assert pyramid.best_level_for_scale(1.0) == 0
    pyramid.close()
    store.close()
