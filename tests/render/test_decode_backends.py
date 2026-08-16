"""Decode-backend tests: pyvips streaming vs PIL/imagecodecs full-frame bound.

Covers the archived pyvips-streaming plan's Phase 1/4 contract (private improve-imgsli-internal-docs repo):
- `from_path` streams (no MAX_SUPPORTED_IMAGE_DIMENSION bound) when the
  installed libvips can stream the file's format;
- the PIL/imagecodecs fallback always enforces the bound;
- previews use the streaming path when available;
- the per-format capability probe (`pyvips_can_stream`) is consistent.

Environment note: the dev `venv/` resolves pyvips to `pyvips-binary`
(no libjxl), so JXL-specific assertions are written against
`pyvips_can_stream` rather than hardcoding a capability.
"""

from __future__ import annotations

import os

import numpy as np
from PIL import Image

from core.constants import AppConstants
from shared.image_processing import progressive_loader as pl
from shared.image_processing.tiled_pixel_store import TiledPixelStore


def _write_rgba_png(path: str, width: int, height: int) -> None:
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    arr[:, :, :3] = 128
    arr[:, :, 3] = 255
    Image.fromarray(arr, mode="RGBA").save(path, format="PNG")


def _can_stream_any() -> bool:
    """Whether the current env can stream *any* format via pyvips."""
    return pl.PYVIPS_SUPPORTED and bool(pl._vips_suffixes())


def test_pyvips_can_stream_is_per_format(tmp_path):
    png = tmp_path / "a.png"
    _write_rgba_png(str(png), 8, 8)
    if pl.PYVIPS_SUPPORTED:
        assert pl.pyvips_can_stream(str(png)) is True
        assert pl.pyvips_can_stream(str(png) + ".qzx") is False
    else:
        assert pl.pyvips_can_stream(str(png)) is False


def test_from_path_streams_oversized_image_when_backend_can(tmp_path):
    big = tmp_path / "big.png"
    _write_rgba_png(str(big), AppConstants.MAX_SUPPORTED_IMAGE_DIMENSION + 1000, 10)

    if _can_stream_any():
        store = TiledPixelStore.from_path(str(big))
        try:
            assert store.size == (AppConstants.MAX_SUPPORTED_IMAGE_DIMENSION + 1000, 10)
        finally:
            store.close()
    else:
        try:
            TiledPixelStore.from_path(str(big))
        except pl.ImageSizeLimitError:
            pass
        else:
            raise AssertionError("PIL fallback must enforce MAX_SUPPORTED_IMAGE_DIMENSION")


def test_from_path_enforces_bound_on_non_streamable_extension(tmp_path):
    """A >65536 file whose extension pyvips can't stream must hit the bound
    even when pyvips is installed (the fallback backend is PIL/imagecodecs)."""
    fake = tmp_path / "huge.qzx"
    _write_rgba_png(str(fake), AppConstants.MAX_SUPPORTED_IMAGE_DIMENSION + 1000, 10)
    assert pl.pyvips_can_stream(str(fake)) is False

    try:
        TiledPixelStore.from_path(str(fake))
    except pl.ImageSizeLimitError:
        pass
    else:
        raise AssertionError("Non-streamable >65536 file must raise ImageSizeLimitError")


def test_small_image_loads_regardless_of_backend(tmp_path):
    png = tmp_path / "small.png"
    _write_rgba_png(str(png), 64, 48)
    store = TiledPixelStore.from_path(str(png))
    try:
        assert store.size == (64, 48)
        assert store.mode == "RGBA"
    finally:
        store.close()


def test_load_preview_image_bounded_streaming_path(tmp_path):
    from PySide6.QtGui import QImage

    png = tmp_path / "wide.png"
    _write_rgba_png(str(png), 2048, 40)

    preview = pl.load_preview_image(str(png))
    assert isinstance(preview, QImage)
    assert preview.format() == QImage.Format.Format_RGBA8888
    assert max(preview.width(), preview.height()) <= 1024
    assert preview.width() == 1024 or preview.height() == 1024


def test_get_image_dimensions_oversized_with_streaming(tmp_path):
    big = tmp_path / "big.png"
    _write_rgba_png(str(big), AppConstants.MAX_SUPPORTED_IMAGE_DIMENSION + 1000, 10)
    if _can_stream_any():
        assert pl.get_image_dimensions(str(big)) == (
            AppConstants.MAX_SUPPORTED_IMAGE_DIMENSION + 1000,
            10,
        )
    else:
        try:
            pl.get_image_dimensions(str(big))
        except pl.ImageSizeLimitError:
            pass
        else:
            raise AssertionError("dimensions probe must enforce the bound without pyvips")


def test_auto_crop_vips_and_pil_agree(tmp_path):
    from shared.image_processing.resize import get_auto_crop_box
    from shared.image_processing.tiled_pixel_store import _find_trim_box_vips

    arr = np.zeros((60, 80, 4), dtype=np.uint8)
    arr[10:50, 20:60, :3] = 200
    arr[10:50, 20:60, 3] = 255
    rgba = Image.fromarray(arr, mode="RGBA")

    vips_box = _find_trim_box_vips(np.asarray(rgba), threshold=15)
    pil_box = get_auto_crop_box(rgba, 15)

    if vips_box is not None:
        assert pil_box is not None, "PIL auto-crop disagreed with vips find_trim"
        assert tuple(int(v) for v in vips_box) == tuple(pil_box)
    # When pyvips is absent vips_box is None and the PIL path is authoritative;
    # nothing to assert there beyond running without error.


def test_forced_pil_fallback_still_enforces_bound(monkeypatch, tmp_path):
    """Force the no-pyvips path even when pyvips is installed, so the PIL
    fallback branch is exercised in every environment."""
    monkeypatch.setattr(pl, "PYVIPS_SUPPORTED", False)
    pl._vips_suffixes_cache = frozenset()
    assert pl.pyvips_can_stream("anything.png") is False

    big = tmp_path / "big.png"
    _write_rgba_png(str(big), AppConstants.MAX_SUPPORTED_IMAGE_DIMENSION + 1000, 10)
    try:
        TiledPixelStore.from_path(str(big))
    except pl.ImageSizeLimitError:
        pass
    else:
        raise AssertionError("PIL fallback must enforce MAX_SUPPORTED_IMAGE_DIMENSION")

    small = tmp_path / "small.png"
    _write_rgba_png(str(small), 32, 24)
    store = TiledPixelStore.from_path(str(small))
    try:
        assert store.size == (32, 24)
    finally:
        store.close()


def test_stream_failure_falls_back_with_bound(monkeypatch, tmp_path):
    """pyvips is installed and the file's format is streamable, but the
    stream attempt itself raises -> the PIL/imagecodecs fallback must still
    enforce MAX_SUPPORTED_IMAGE_DIMENSION."""
    if not _can_stream_any():
        return

    import shared.image_processing.tiled_pixel_store as tps

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated stream failure")

    big = tmp_path / "big.png"
    _write_rgba_png(str(big), AppConstants.MAX_SUPPORTED_IMAGE_DIMENSION + 1000, 10)
    assert pl.pyvips_can_stream(str(big)) is True

    monkeypatch.setattr(tps, "_stream_pyvips_to_memmap", _boom)
    try:
        TiledPixelStore.from_path(str(big))
    except pl.ImageSizeLimitError:
        pass
    else:
        raise AssertionError("stream-failure fallback must enforce the bound")


def test_jxl_probe_consistent_with_suffixes():
    assert pl.pyvips_can_stream("sample.JXL") == (".jxl" in pl._vips_suffixes())
    assert pl.pyvips_can_stream("sample.jpg") == (".jpg" in pl._vips_suffixes())


def test_auto_crop_end_to_end_streaming_matches_pil(monkeypatch, tmp_path):
    """Auto-crop through the pyvips streaming path and the PIL fallback must
    agree on the crop box for the same source (the two paths use different
    probes: pyvips thumbnail+find_trim vs the PIL get_auto_crop_box probe)."""
    arr = np.zeros((200, 300, 4), dtype=np.uint8)
    arr[30:170, 40:260, :3] = 180
    arr[30:170, 40:260, 3] = 255
    path = tmp_path / "margins.png"
    Image.fromarray(arr, mode="RGBA").save(str(path), format="PNG")

    if not _can_stream_any():
        store = TiledPixelStore.from_path(str(path), auto_crop=True)
        try:
            assert store.size == (220, 140)
        finally:
            store.close()
        return

    store_stream = TiledPixelStore.from_path(str(path), auto_crop=True)
    try:
        size_stream = store_stream.size
    finally:
        store_stream.close()

    monkeypatch.setattr(pl, "PYVIPS_SUPPORTED", False)
    pl._vips_suffixes_cache = frozenset()
    store_pil = TiledPixelStore.from_path(str(path), auto_crop=True)
    try:
        size_pil = store_pil.size
    finally:
        store_pil.close()

    assert size_pil == (220, 140)
    assert size_stream == size_pil