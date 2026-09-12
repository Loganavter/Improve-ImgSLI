"""Tests for GEGL-style TiledPixelStore."""

import numpy as np
from PIL import Image

from core.constants import AppConstants
from shared.image_processing.tiled_pixel_store import (
    TiledPixelStore,
    close_pixel_store,
    maybe_wrap_pixel_store,
)


def _gradient_image(width=64, height=48):
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    arr[:, :, 0] = np.arange(width, dtype=np.uint8)[None, :]
    arr[:, :, 1] = np.arange(height, dtype=np.uint8)[:, None]
    arr[:, :, 2] = 128
    arr[:, :, 3] = 255
    return Image.fromarray(arr, mode="RGBA")


def test_crop_matches_direct_pil_crop():
    original = _gradient_image()
    store = TiledPixelStore.from_pil(original)
    box = (10, 5, 40, 30)

    cropped = store.crop(box)
    expected = original.crop(box)

    assert cropped.size == expected.size
    assert list(cropped.tobytes()) == list(expected.tobytes())
    store.close()


def test_read_tile_covers_grid():
    ts = AppConstants.PIXEL_TILE_SIZE
    original = _gradient_image(width=ts + 10, height=ts + 5)
    store = TiledPixelStore.from_pil(original)

    assert store.tile_rows == 2
    assert store.tile_cols == 2

    tile00 = store.read_tile(0, 0)
    assert tile00.size == (ts, ts)
    expected = original.crop((0, 0, ts, ts))
    assert list(tile00.tobytes()) == list(expected.tobytes())

    tile11 = store.read_tile(1, 1)
    assert tile11.size == (10, 5)
    store.close()


def test_materialize_full_round_trip():
    original = _gradient_image()
    store = TiledPixelStore.from_pil(original)
    restored = store.materialize_full()
    assert restored.size == original.size
    assert list(restored.tobytes()) == list(original.tobytes())
    store.close()


def test_from_path_round_trip(tmp_path):
    path = tmp_path / "sample.png"
    original = _gradient_image()
    original.save(path)

    store = TiledPixelStore.from_path(path)
    assert store.size == original.size
    store.close()


def test_close_and_reopen_from_disk(tmp_path):
    path = tmp_path / "persist.png"
    original = _gradient_image(width=48, height=32)
    original.save(path)

    with TiledPixelStore.from_path(path) as store:
        assert store.size == (48, 32)

    reopened = TiledPixelStore.from_path(path)
    try:
        assert reopened.size == (48, 32)
        assert list(reopened.crop((0, 0, 8, 8)).tobytes()) == list(
            original.crop((0, 0, 8, 8)).tobytes()
        )
    finally:
        reopened.close()


def test_crop_does_not_materialize_full(monkeypatch):
    original = _gradient_image(width=256, height=256)
    store = TiledPixelStore.from_pil(original)

    def _fail_materialize():
        raise AssertionError("materialize_full must not run for region crop")

    monkeypatch.setattr(store, "materialize_full", _fail_materialize)
    cropped = store.crop((10, 10, 50, 50))
    assert cropped.size == (40, 40)
    store.close()


def test_maybe_wrap_always_returns_store():
    small = _gradient_image(width=32, height=32)
    result = maybe_wrap_pixel_store(small)
    assert isinstance(result, TiledPixelStore)
    close_pixel_store(result)


def test_maybe_wrap_none_is_noop():
    assert maybe_wrap_pixel_store(None) is None


def test_close_pixel_store_noop_for_plain_pil():
    plain = _gradient_image()
    close_pixel_store(plain)
    assert plain.size == (64, 48)


def test_from_pil_strip_spill_pixel_parity():
    """Strip write must match a full-buffer spill (gradient, multi-tile)."""
    ts = AppConstants.PIXEL_TILE_SIZE
    original = _gradient_image(width=ts + 17, height=ts + 9)
    store = TiledPixelStore.from_pil(original)
    try:
        restored = store.materialize_full()
        assert restored.size == original.size
        assert list(restored.tobytes()) == list(original.tobytes())
    finally:
        store.close()


def test_from_path_auto_crop_shrinks_black_border(tmp_path):
    # White content inset in a black frame.
    canvas = Image.new("RGBA", (200, 160), (0, 0, 0, 255))
    content = Image.new("RGBA", (120, 80), (200, 180, 160, 255))
    canvas.paste(content, (40, 40))
    path = tmp_path / "bordered.png"
    canvas.save(path)

    store = TiledPixelStore.from_path(path, auto_crop=True)
    try:
        w, h = store.size
        assert w < 200 and h < 160
        assert w >= 100 and h >= 60
        # Interior should be the light content color, not black.
        mid = store.crop((w // 2, h // 2, w // 2 + 1, h // 2 + 1)).getpixel((0, 0))
        assert mid[0] > 100
    finally:
        store.close()


def test_from_path_auto_crop_near_fullres_bbox(tmp_path):
    """Downscale-probe crop stays within a few px of full-res crop_black_borders."""
    from shared.image_processing.resize import crop_black_borders

    canvas = Image.new("RGBA", (400, 300), (0, 0, 0, 255))
    content = Image.new("RGBA", (220, 160), (180, 170, 160, 255))
    canvas.paste(content, (90, 70))
    path = tmp_path / "bordered_hi.png"
    canvas.save(path)

    expected = crop_black_borders(canvas)
    store = TiledPixelStore.from_path(path, auto_crop=True)
    try:
        sw, sh = store.size
        ew, eh = expected.size
        assert abs(sw - ew) <= 4
        assert abs(sh - eh) <= 4
    finally:
        store.close()


def test_from_pil_does_not_asarray_full_image(monkeypatch):
    """Spill must not allocate one HxWx4 numpy copy of the whole PIL image."""
    import shared.image_processing.tiled_pixel_store as tps

    ts = AppConstants.PIXEL_TILE_SIZE
    original = _gradient_image(width=96, height=ts + 40)
    full_calls: list[tuple[int, ...]] = []
    real_asarray = np.asarray

    def spy_asarray(obj, *args, **kwargs):
        arr = real_asarray(obj, *args, **kwargs)
        if isinstance(arr, np.ndarray) and arr.ndim == 3 and arr.shape[:2] == (
            original.height,
            original.width,
        ):
            full_calls.append(arr.shape)
        return arr

    monkeypatch.setattr(tps.np, "asarray", spy_asarray)
    store = tps.TiledPixelStore.from_pil(original)
    try:
        assert not full_calls, f"unexpected full asarray shapes: {full_calls}"
        assert store.size == original.size
    finally:
        store.close()


def test_close_removes_backing_file():
    store = TiledPixelStore.from_pil(_gradient_image())
    path = store._path
    store.close()
    import os

    assert not os.path.exists(path)
