"""Tiled full-resolution artifact runner (services/artifact_tiles).

The stage-2 catalog runs on a bounded proxy, which destroys the 8x8 DCT block
grid and averages thin chroma rims away. The tiled runner walks the
full-resolution source (tile <= 512 so the detectors never hit their own
downscale), runs the existing ``analyze_images`` per tile, and aggregates the
worst-of-tiles severity.

Guarded here:
- blocking / thin chroma rims that the 512 downscale misses are caught tiled;
- self-pair (candidate == source) abstains to all-clean even on biased content;
- a small (<= 512) image is exactly equivalent to ``analyze_images``;
- the runner never materializes the full frame (bounded memory);
- every crop origin is phase-aligned (multiple of 8) and no crop exceeds the
  tile, so a clean gradient across tile seams is not manufactured into
  blocking/halo.
"""

from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("PIL")
pytest.importorskip("skimage")

from PIL import Image  # noqa: E402

from tabs.image_gallery.services.artifact_tiles import (  # noqa: E402
    analyze_artifacts_tiled,
    tile_crop_boxes,
)
from tabs.image_gallery.services.artifacts import (  # noqa: E402
    Artifact,
    Severity,
    analyze_images,
)


def _downscale(img: Image.Image, edge: int = 512) -> Image.Image:
    w, h = img.size
    longest = max(w, h)
    if longest <= edge:
        return img
    scale = edge / longest
    return img.resize(
        (max(1, int(w * scale)), max(1, int(h * scale))), Image.BILINEAR
    )


def _blocky(width: int = 1920, height: int = 1080, offset: int = 24) -> Image.Image:
    """8x8 DCT-like blocks: strong block-boundary steps + a 1px intra-block ramp.

    The tiny ramp keeps the interior mean above the detector's zero guard
    (``_to_gray_array`` inside ``detect_blocking`` bails to 0.0 when the
    interior is identical), so the boundary/interior ratio is huge (~24x).
    """
    x = np.arange(width)
    ramp = (x % 8)
    bx = x // 8
    by = np.arange(height) // 8
    dc = ((bx[None, :] + by[:, None]) % 2) * offset
    base = np.clip(ramp[None, :] + dc, 0, 255).astype(np.uint8)
    return Image.fromarray(np.dstack([base, base, base]), "RGB")


def _shift_channel(channel: np.ndarray, shift: int) -> np.ndarray:
    out = np.empty_like(channel)
    out[:, :shift] = channel[:, :1]
    out[:, shift:] = channel[:, :-shift]
    return out


def _chroma_rim(
    width: int = 1920,
    height: int = 1080,
    *,
    edge: int = 700,
    shift: int = 3,
    band: int = 2,
    lo: int = 40,
    hi: int = 200,
) -> Image.Image:
    """A thin bright rim with the R channel shifted laterally (chroma fringe)."""
    arr = np.full((height, width, 3), lo, np.uint8)
    arr[:, edge : edge + band] = (hi, hi, hi)
    out = arr.copy()
    out[:, :, 0] = _shift_channel(arr[:, :, 0], shift)
    return Image.fromarray(out, "RGB")


def _sine_gradient(width: int = 1920, height: int = 1080) -> Image.Image:
    x = np.arange(width)
    sig = (128 + 100 * np.sin(x / 37.0)).astype(np.uint8)
    arr = np.tile(sig, (height, 1))
    return Image.fromarray(np.dstack([arr, arr, arr]), "RGB")


def test_blocking_survives_tiling_while_downscale_misses() -> None:
    img = _blocky()
    tiled = analyze_artifacts_tiled(img)
    assert tiled[Artifact.BLOCKING] != Severity.CLEAN

    downscaled = _downscale(img)
    assert downscaled.size != img.size
    assert analyze_images(downscaled, None)[Artifact.BLOCKING] == Severity.CLEAN


def test_thin_chroma_rim_survives_tiling_while_downscale_misses() -> None:
    img = _chroma_rim()
    tiled = analyze_artifacts_tiled(img)
    assert tiled[Artifact.CHROMA_FRINGING] != Severity.CLEAN

    downscaled = _downscale(img)
    assert analyze_images(downscaled, None)[Artifact.CHROMA_FRINGING] == Severity.CLEAN


def test_self_pair_abstains_to_clean() -> None:
    # Biased content that would otherwise flag as blocking on its own.
    img = _blocky()
    got = analyze_artifacts_tiled(img, source_image=img)
    assert set(got) == set(Artifact)
    assert all(got[art] == Severity.CLEAN for art in Artifact), got


def test_none_source_is_all_clean() -> None:
    got = analyze_artifacts_tiled(None)
    assert set(got) == set(Artifact)
    assert all(got[art] == Severity.CLEAN for art in Artifact), got


def test_small_image_equivalent_to_direct_analyze() -> None:
    item = _chroma_rim(width=300, height=200, edge=150)
    source = _blocky(width=300, height=200)
    tiled = analyze_artifacts_tiled(item, source_image=source)
    direct = analyze_images(item, source)
    assert tiled == direct


def test_workers_match_serial() -> None:
    img = _blocky()
    assert analyze_artifacts_tiled(img, workers=1) == analyze_artifacts_tiled(
        img, workers=4
    )


def test_bounded_memory_never_materializes_full_frame(monkeypatch, tmp_path) -> None:
    from engine.store.tiled_pixel_store import TiledPixelStore

    big = np.random.default_rng(0).integers(
        0, 255, (1500, 2000, 4), dtype=np.uint8
    )
    store = TiledPixelStore.from_pil(
        Image.fromarray(big, "RGBA"), tmp_dir=str(tmp_path)
    )
    try:

        def _boom(self):  # pragma: no cover - must never run
            raise AssertionError("materialize_full must not be called")

        monkeypatch.setattr(TiledPixelStore, "materialize_full", _boom)
        got = analyze_artifacts_tiled(store)
        assert set(got) == set(Artifact)
        assert store.is_open
    finally:
        store.close()


def test_crop_boxes_are_phase_aligned_bounded_and_cover() -> None:
    width, height, tile = 1920, 1080, 512
    boxes = tile_crop_boxes(width, height, tile=tile, overlap=8)
    assert boxes
    for left, top, right, bottom in boxes:
        assert left % 8 == 0 and top % 8 == 0, (left, top)
        assert right - left <= tile and bottom - top <= tile
        assert right > left and bottom > top
    covered = np.zeros((height, width), dtype=bool)
    for left, top, right, bottom in boxes:
        covered[top:bottom, left:right] = True
    assert covered.all()


def test_clean_gradient_across_seams_not_manufactured() -> None:
    got = analyze_artifacts_tiled(_sine_gradient())
    assert got[Artifact.BLOCKING] == Severity.CLEAN, got
    assert got[Artifact.HALO] == Severity.CLEAN, got
