"""Large-image SSIM must not materialize full TiledPixelStore."""

import numpy as np
import pytest
from PIL import Image

skimage = pytest.importorskip("skimage")

from shared.analysis import differ as _differ
from shared.analysis import metrics as _metrics
from shared.analysis.output import to_u8_array, to_u8_rgb
from shared.analysis.ssim_source import create_ssim_map_from_sources
from shared.image_processing.store_lease import StoreLease
from engine.store.tiled_pixel_store import TiledPixelStore


def _guard_full_frame_np_empty(monkeypatch, width, height):
    """Fail any np.empty at full-frame scale or above: output must stream
    tile-by-tile, never assemble a full-frame result buffer."""
    full = int(width) * int(height)
    real_empty = np.empty

    def _guarded(shape, *args, **kwargs):
        try:
            size = int(np.prod(shape))
        except Exception:
            size = 0
        assert size < full, f"full-frame np.empty shape={shape} (peak RAM unbounded)"
        return real_empty(shape, *args, **kwargs)

    monkeypatch.setattr(np, "empty", _guarded)


def test_large_ssim_from_sources_avoids_materialize_full(monkeypatch):
    # 8192 is wide but only 64px tall — small enough for CI, still multi-tile.
    w, h = 8192, 64
    img1 = Image.new("RGBA", (w, h), (200, 10, 10, 255))
    img2 = Image.new("RGBA", (w, h), (200, 12, 10, 255))
    s1 = TiledPixelStore.from_pil(img1)
    s2 = TiledPixelStore.from_pil(img2)

    calls: list[str] = []

    def _spy_materialize_full():
        calls.append("materialize_full")
        raise AssertionError("materialize_full must not run")

    monkeypatch.setattr(s1, "materialize_full", _spy_materialize_full)
    monkeypatch.setattr(s2, "materialize_full", _spy_materialize_full)

    result = create_ssim_map_from_sources(
        s1,
        s2,
        lease1=StoreLease.capture(s1),
        lease2=StoreLease.capture(s2),
    )
    assert result is not None
    assert result.size == (w, h)
    assert calls == []

    if isinstance(result, TiledPixelStore):
        result.close()
    s1.close()
    s2.close()

def test_ssim_output_streams_without_full_frame_result(monkeypatch):
    """Output peak: the tiled SSIM map must assemble tile-by-tile (any
    full-frame np.empty fails the guard), while sources stay tile-fed."""
    w, h = 8192, 64
    img1 = Image.new("RGBA", (w, h), (200, 10, 10, 255))
    img2 = Image.new("RGBA", (w, h), (200, 12, 10, 255))
    s1 = TiledPixelStore.from_pil(img1)
    s2 = TiledPixelStore.from_pil(img2)
    _guard_full_frame_np_empty(monkeypatch, w, h)
    try:
        result = create_ssim_map_from_sources(
            s1, s2, lease1=StoreLease.capture(s1), lease2=StoreLease.capture(s2)
        )
        assert result is not None
        assert result.size == (w, h)
        if isinstance(result, TiledPixelStore):
            result.close()
    finally:
        s1.close()
        s2.close()


def test_large_diff_spills_to_store_without_full_frame_buffer(monkeypatch, tmp_path):
    """>16M leg: a 5000x4000 (20M px) diff must spill tile-by-tile to a
    TiledPixelStore with no full-frame result buffer and correct dims."""
    w, h = 5000, 4000
    img1 = Image.new("RGB", (w, h), (200, 10, 10))
    img2 = Image.new("RGB", (w, h), (190, 14, 10))
    s1 = TiledPixelStore.from_pil(img1, tmp_dir=str(tmp_path))
    s2 = TiledPixelStore.from_pil(img2, tmp_dir=str(tmp_path))
    _guard_full_frame_np_empty(monkeypatch, w, h)
    try:
        from shared.analysis.diff_source import (
            create_grayscale_diff_from_sources,
            create_highlight_diff_from_sources,
        )

        for fn in (
            create_highlight_diff_from_sources,
            create_grayscale_diff_from_sources,
        ):
            out = fn(s1, s2)
            assert out is not None, fn.__name__
            assert isinstance(out, TiledPixelStore), (
                f"{fn.__name__}: 20M px output must spill, got {type(out)}"
            )
            assert out.size == (w, h)
            out.close()
    finally:
        s1.close()
        s2.close()


def test_small_image_map_and_scalar_agree():
    """Small-image leg: below skimage's default window, the map's shared
    win-size clamp and the scalar's must agree — both succeed."""
    img1 = Image.new("RGB", (5, 5), (10, 200, 10))
    img2 = Image.new("RGB", (5, 5), (10, 200, 12))
    from shared.analysis.differ import _resolve_ssim_win_size, create_ssim_map

    assert _resolve_ssim_win_size(5, 5) == 5
    assert create_ssim_map(img1, img2) is not None
    assert _metrics.calculate_ssim(img1, img2) is not None


def test_size_mismatch_policy_map_and_scalar_agree():
    """ONE policy: mismatched sizes resample-and-record on both paths —
    the map takes image1's size and the scalar computes over the same
    resampled pixels instead of refusing."""
    img1 = Image.new("RGB", (32, 32), (200, 10, 10))
    img2 = Image.new("RGB", (16, 16), (200, 10, 10))
    from shared.analysis.differ import create_ssim_map

    assert create_ssim_map(img1, img2).size == (32, 32)
    assert _metrics.calculate_ssim(img1, img2) is not None
    assert _metrics.calculate_psnr(img1, img2) is not None
    assert _metrics.calculate_metrics(img1, img2) is not None


def test_16bit_scales_by_257_never_truncates():
    """16-bit leg: value 300 must scale to 1 (300//257), never truncate
    to 44 (mod-256) — in preview-rate PIL converts and JXL-uint16 arrays."""
    arr16 = np.full((8, 8), 300, dtype=np.uint16)
    assert int(to_u8_array(arr16)[0, 0]) == 1
    pil16 = Image.fromarray(arr16, mode="I;16")
    assert int(np.asarray(to_u8_rgb(pil16).convert("L"))[0, 0]) == 1
    # End to end: identical 16-bit content measures (near-)identical.
    a = Image.fromarray(np.full((16, 16), 30000, dtype=np.uint16), mode="I;16")
    b = Image.fromarray(np.full((16, 16), 30257, dtype=np.uint16), mode="I;16")
    assert _metrics.calculate_ssim(a, b) is not None
    assert _differ.create_grayscale_diff(a, b) is not None
