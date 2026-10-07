"""Halo detector: overshoot vs a plain crisp/cel step edge.

The old ring-Laplacian heuristic flagged *any* strong edge as a halo — a
crisp cel-shaded cartoon (Tom & Jerry) read as "strong halo" while the VLM
saw none. The detector now measures overshoot beyond the local edge plateau,
so a plain step edge reads clean while genuine sharpening overshoot flags.
"""

from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("PIL")

from PIL import Image, ImageFilter  # noqa: E402


def _cel() -> Image.Image:
    """Flat colour blocks with hard edges — a cartoon/cel stand-in."""
    a = np.zeros((128, 128, 3), np.uint8)
    a[:, :] = (30, 60, 180)
    a[20:108, 30:98] = (220, 180, 40)
    a[50:78, 55:75] = (20, 20, 20)
    return Image.fromarray(a, "RGB")


def test_cel_step_edge_is_not_halo() -> None:
    """A crisp flat-colour edge is a step, not an overshoot (the reported FP)."""
    from tabs.image_gallery.services.artifacts import Severity, detect_halo

    assert detect_halo(_cel()) == Severity.CLEAN


def test_oversharpened_edge_flags_halo() -> None:
    """Genuine sharpening overshoot past the plateau still flags."""
    from tabs.image_gallery.services.artifacts import Severity, detect_halo

    sharp = _cel().filter(ImageFilter.UnsharpMask(radius=3, percent=100, threshold=0))
    assert detect_halo(sharp) == Severity.FLAGGED
