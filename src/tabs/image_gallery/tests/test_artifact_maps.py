"""Coarse artifact localization (services/artifact_maps.localize).

SalArt-VQA grounding: a claim should point at *where* the artifact is. The
heatmap is a coarse tile grid, so the test only asserts it exists and is hotter
where the artifact actually is — not exact values.
"""

from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("PIL")

from PIL import Image  # noqa: E402


def _half_banded() -> Image.Image:
    """Left half a smooth ramp (clean), right half posterized (banded)."""
    x = np.linspace(0, 255, 128).astype(np.uint8)
    a = np.tile(x, (64, 1))
    a[:, 64:] = ((a[:, 64:] // 16) * 16).astype(np.uint8)
    return Image.fromarray(a, "L").convert("RGB")


def test_localize_returns_grid_hotter_where_artifact_is() -> None:
    from tabs.image_gallery.services.artifact_maps import localize
    from tabs.image_gallery.services.artifacts import Artifact

    m = localize(_half_banded(), Artifact.BANDING, None, grid=4)
    assert m is not None and len(m) == 4 and all(len(r) == 4 for r in m)
    left = max(m[y][x] for y in range(4) for x in range(2))
    right = max(m[y][x] for y in range(4) for x in range(2, 4))
    assert right >= left
    assert right > 0.0  # the banded half fired somewhere


def test_localize_unknown_or_missing_is_none() -> None:
    from tabs.image_gallery.services.artifact_maps import localize

    assert localize(_half_banded(), "not-an-artifact", None) is None
    assert localize(None, "banding", None) is None
