"""Blocking must be honest about the 8×8 block grid at native resolution.

The 8-px DCT grid only exists on unresampled pixels: the boundary phase
``(x + 1) % 8 == 0`` is meaningless once a caller has resized the image. The
old ``detect_blocking`` fed every input through ``_to_gray_array`` (default
``max_edge=512``), so any input whose longest edge exceeded 512 was silently
downscaled and a real blocky 1920 frame read CLEAN.

Contract pinned here:
- a **native** tile/frame whose origin is a multiple of 8 (the tiled runner,
  or a full image at origin 0) is analysed pixel-for-pixel and flags a genuine
  block grid;
- a **downscaled** input has no native 8-px grid to find and reads CLEAN —
  an honest abstention, never a mis-phased severity (the documented miss);
- a smooth gradient stays CLEAN at every resolution (false-positive guard);
- an input larger than ``_BLOCKING_MAX_NATIVE_EDGE`` abstains rather than
  being blind-resampled.
"""

from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("PIL")

from PIL import Image  # noqa: E402

from tabs.image_gallery.services.artifacts import (  # noqa: E402
    _BLOCKING_MAX_NATIVE_EDGE,
    Severity,
    detect_blocking,
)


def _blocky_frame(w: int, h: int, *, seed: int = 0, block: int = 8, amp: int = 40) -> Image.Image:
    """Smooth-ish base with a per-8×8-block DC offset (a JPEG block grid).

    The base carries a small intra-block texture so non-boundary diffs are
    non-zero (the detector's ratio must be well defined), while the block
    offsets make boundary diffs much larger.
    """
    rng = np.random.default_rng(seed)
    x = np.arange(w)[None, :]
    y = np.arange(h)[:, None]
    stripe = ((x % block) - block / 2.0) * 2.0
    base = 128.0 + stripe + ((y % 7) - 3)
    offsets = rng.integers(-amp, amp + 1, size=(h // block + 1, w // block + 1))
    off = np.kron(offsets, np.ones((block, block), dtype=np.float32))[:h, :w]
    arr = np.clip(base + off, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "L").convert("RGB")


def _smooth(w: int, h: int) -> Image.Image:
    x = np.linspace(0, 255, w)[None, :]
    arr = np.tile(x, (h, 1)).astype(np.uint8)
    return Image.fromarray(arr, "L").convert("RGB")


def _downscale(im: Image.Image, edge: int) -> Image.Image:
    w, h = im.size
    m = max(w, h)
    if m <= edge:
        return im
    s = edge / m
    return im.resize((max(1, int(w * s)), max(1, int(h * s))), Image.BILINEAR)


def test_native_blocky_tile_flags() -> None:
    """(a) A native 480×360 tile (origin 0) exposes its 8-px grid."""
    got = detect_blocking(_blocky_frame(480, 360, seed=1))
    assert got in (Severity.MILD, Severity.FLAGGED), got


def test_native_blocky_tile_at_multiple_of_8_origin_flags() -> None:
    """The tiled-runner contract: a crop at an 8-aligned origin keeps phase."""
    frame = _blocky_frame(1920, 1440, seed=1)
    # origin (240, 160) is a multiple of 8; the crop is a native tile.
    tile = frame.crop((240, 160, 240 + 480, 160 + 360))
    got = detect_blocking(tile)
    assert got in (Severity.MILD, Severity.FLAGGED), got


def test_downscaled_blocky_content_abstains_clean() -> None:
    """(b) The SAME blocky content downscaled to 512 has no native 8-px grid.

    This is the honest miss: resampling destroys the phase, so the detector
    must read CLEAN rather than report a mis-phased severity.
    """
    big = _blocky_frame(1920, 1440, seed=1)
    proxy = _downscale(big, 512)
    assert max(proxy.size) == 512
    assert detect_blocking(proxy) == Severity.CLEAN


def test_smooth_gradient_stays_clean() -> None:
    """(c) False-positive guard: no block structure, native or downscaled."""
    native = _smooth(480, 360)
    assert detect_blocking(native) == Severity.CLEAN
    assert detect_blocking(_downscale(_smooth(1920, 1440), 512)) == Severity.CLEAN


def test_native_above_512_is_analysed_natively() -> None:
    """(d) We chose native analysis: a native >=512 blocky frame still flags.

    No silent downscale: the 1920-wide frame is well under the native cap, so
    it is analysed pixel-for-pixel (the regression that used to read CLEAN).
    """
    assert max(_blocky_frame(1920, 1440, seed=1).size) > 512
    got = detect_blocking(_blocky_frame(1920, 1440, seed=1))
    assert got in (Severity.MILD, Severity.FLAGGED), got


def test_oversized_input_abstains_clean() -> None:
    """Above the native cap the grid cannot be trusted → honest CLEAN."""
    assert _BLOCKING_MAX_NATIVE_EDGE == 2048
    huge = _blocky_frame(_BLOCKING_MAX_NATIVE_EDGE + 8, 512, seed=3)
    assert max(huge.size) > _BLOCKING_MAX_NATIVE_EDGE
    assert detect_blocking(huge) == Severity.CLEAN
