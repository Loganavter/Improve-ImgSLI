"""P2 shared: resample_image_subpixel honors the float box.

The old implementation truncated every coordinate with ``int()``, so
boxes differing only fractionally (10.2 vs 10.7) produced byte-identical
output. The rewrite translates the expanded crop by the fractional
remainder (BICUBIC shift) so the integer window aligns with the float
box: POSITION is subpixel-exact (fractional offsets change pixels),
SIZE stays whole-px (absorbed by the resize to target).
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from shared.image_processing.resize import resample_image_subpixel


def _noise_image(seed=7, size=(64, 64)):
    rng = np.random.default_rng(seed)
    return Image.fromarray((rng.random((*size[::-1], 3)) * 255).astype(np.uint8), "RGB")


def test_fractional_offset_changes_pixels():
    img = _noise_image()
    out_a = resample_image_subpixel(img, (10.2, 10.2, 40.2, 40.2), (30, 30), "LANCZOS", False)
    out_b = resample_image_subpixel(img, (10.7, 10.7, 40.7, 40.7), (30, 30), "LANCZOS", False)
    assert out_a.size == (30, 30) == out_b.size
    assert not np.array_equal(np.asarray(out_a), np.asarray(out_b))


def test_half_pixel_shift_moves_content():
    # Sharp vertical edge: a 0.5px box shift must move the edge response.
    arr = np.zeros((32, 64, 3), dtype=np.uint8)
    arr[:, 32:] = 255
    img = Image.fromarray(arr, "RGB")
    out_a = resample_image_subpixel(img, (8.0, 8.0, 56.0, 24.0), (48, 16), "LANCZOS", False)
    out_b = resample_image_subpixel(img, (8.5, 8.0, 56.5, 24.0), (48, 16), "LANCZOS", False)
    col_a = np.asarray(out_a).astype(float)[:, :, 0].mean(axis=0)
    col_b = np.asarray(out_b).astype(float)[:, :, 0].mean(axis=0)
    edge_a = float(np.argmax(col_a > 127))
    edge_b = float(np.argmax(col_b > 127))
    assert abs(edge_b - edge_a) > 0.0


def test_integer_box_matches_direct_crop_resize():
    img = _noise_image()
    out = resample_image_subpixel(img, (10, 10, 40, 40), (30, 30), "LANCZOS", False)
    expected = img.crop((10, 10, 40, 40)).resize((30, 30), Image.Resampling.LANCZOS)
    assert out.size == (30, 30)
    diff = np.abs(np.asarray(out).astype(int) - np.asarray(expected).astype(int))
    assert diff.max() <= 1, "integer box must equal crop+resize up to rounding"


def test_degenerate_and_empty_inputs():
    img = _noise_image()
    blank = resample_image_subpixel(img, (20, 20, 10, 10), (30, 30), "LANCZOS", False)
    assert blank.size == (30, 30)
    assert resample_image_subpixel(img, (10, 10, 20, 20), (0, 0), "LANCZOS", False) is img
    assert resample_image_subpixel(None, (10, 10, 20, 20), (30, 30), "LANCZOS", False) is None


def test_box_outside_image_yields_blank_target():
    img = _noise_image()
    blank = resample_image_subpixel(
        img, (1000.5, 1000.5, 1100.5, 1100.5), (30, 30), "LANCZOS", False
    )
    assert blank.size == (30, 30)
    assert np.asarray(blank).max() == 0
