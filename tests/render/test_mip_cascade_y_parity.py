"""Mip-cascade Y correction is per-backend FAMILY, never unconditional.

Why this exists (plan-tile-policy-reliability-2026-10-24, P0 verdict
2026-10-24): the cascade wrote an UNCONDITIONAL Y-flip into its downsample
vertex stage. On OpenGL and Vulkan that is required; on D3D11 it inverted
every generated level relative to its source, so the chain alternated by
level parity (odd levels upside-down). The tile sampler is trilinear, so any
zoom below 1:1 blended upright mip0 with flipped mip1 -- the "bands / flipped
tiles / a tile fills a third" artifact on the D3D11 host, absent at >= 1:1
(mip0 only) and absent in the magnifier (near 1:1).

Measured from the D3D11 host's ``IMGSLI_TILE_DUMP`` mip readbacks before the
fix: each consecutive level pair matched a vertical flip at mean|delta|
2.4-13, identity at 42-59.

The first attempt gated the flip on ``rhi.isYUpInFramebuffer()``; measured
afterwards, Vulkan reports False there *and* still needs the flip, so that
gate flipped every tile on Vulkan. The gate is therefore the backend family:
skip only on D3D (the one family measured to need none), keep the flip
everywhere else and whenever the backend cannot be queried.
"""

from __future__ import annotations

import pytest
from engine.gpu.mip_cascade import downsample_corr_matrix

_IDENTITY = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)


class _Rhi:
    """Fake QRhi exposing the two documented orientation properties."""

    def __init__(self, y_up_framebuffer: bool, y_up_ndc: bool) -> None:
        self._y_up_framebuffer = y_up_framebuffer
        self._y_up_ndc = y_up_ndc

    def isYUpInFramebuffer(self) -> bool:
        return self._y_up_framebuffer

    def isYUpInNDC(self) -> bool:
        return self._y_up_ndc


class _RhiWithoutQuery:
    """A backend object that exposes neither orientation query."""


def test_d3d_like_backends_do_not_flip():
    """Top-left framebuffer + y-up NDC (D3D11/12, Metal): no flip.

    Red before the fix: the pass flipped unconditionally, so each generated
    level was re-flipped and the chain alternated by parity.
    """
    matrix = downsample_corr_matrix(_Rhi(False, True))
    assert matrix[5] == 1.0, (
        "a top-left framebuffer with y-up NDC must NOT flip the "
        f"mip-downsample pass, got y scale {matrix[5]!r}"
    )
    assert matrix == _IDENTITY, f"correction must be identity here, got {matrix!r}"


def test_vulkan_like_backends_flip():
    """Top-left framebuffer + y-down NDC (Vulkan): the flip is required.

    Red if the gate goes back to ``isYUpInFramebuffer()`` alone: Vulkan
    reports False there, which dropped the flip and flipped every tile.
    """
    matrix = downsample_corr_matrix(_Rhi(False, False))
    assert matrix[5] == -1.0, (
        "a y-down NDC backend must keep the mip-downsample Y flip, got y "
        f"scale {matrix[5]!r} (isYUpInFramebuffer() alone cannot decide this)"
    )


def test_opengl_like_backends_flip():
    """Bottom-left framebuffer + y-up NDC (OpenGL/GLES2): flip required."""
    matrix = downsample_corr_matrix(_Rhi(True, True))
    assert matrix[5] == -1.0, (
        f"OpenGL must keep the mip-downsample Y flip, got y scale {matrix[5]!r}"
    )


def test_missing_orientation_query_keeps_the_flip():
    """Unknown backend: never guess a flip away."""
    matrix = downsample_corr_matrix(_RhiWithoutQuery())
    assert matrix[5] == -1.0, (
        "a backend without the orientation queries must keep the flip, got "
        f"y scale {matrix[5]!r}"
    )


def test_rule_matches_the_measured_backends():
    """The predicate reproduces all three measured backends in one expression."""
    from engine.gpu.rt_y_orientation import sampled_rt_needs_y_flip

    measured = {
        "opengl": (_Rhi(True, True), True),
        "vulkan": (_Rhi(False, False), True),
        "d3d11": (_Rhi(False, True), False),
    }
    for name, (rhi, expected) in measured.items():
        assert sampled_rt_needs_y_flip(rhi) is expected, (
            f"{name}: predicate must return {expected} "
            "(plan-tile-policy-reliability-2026-10-24 measurements)"
        )


@pytest.mark.parametrize(
    "y_up_framebuffer,y_up_ndc",
    [(True, True), (False, False), (False, True)],
)
def test_correction_is_diagonal_for_every_backend(y_up_framebuffer, y_up_ndc):
    """Diagonal for every backend -- the uniform's row/column order cannot matter."""
    matrix = downsample_corr_matrix(_Rhi(y_up_framebuffer, y_up_ndc))
    assert len(matrix) == 16
    for index in (1, 2, 3, 4, 6, 7, 8, 9, 11, 12, 13, 14):
        assert matrix[index] == 0.0, (
            f"correction matrix must be diagonal (index {index} = "
            f"{matrix[index]!r}, y_up_fb={y_up_framebuffer})"
        )
    assert (matrix[0], matrix[10], matrix[15]) == (1.0, 1.0, 1.0)
