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
from PySide6.QtGui import QRhi

from engine.gpu.mip_cascade import downsample_corr_matrix

_IDENTITY = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)


class _Rhi:
    def __init__(self, backend) -> None:
        self._backend = backend

    def backend(self):
        return self._backend


class _RhiWithoutQuery:
    """A backend object that does not expose ``backend()``."""


def test_d3d_backends_do_not_flip():
    """D3D11/12: applying the flip re-flips every level (the shipped bug)."""
    for name in ("D3D11", "D3D12"):
        backend = getattr(QRhi.Implementation, name, None)
        if backend is None:
            continue
        matrix = downsample_corr_matrix(_Rhi(backend))
        assert matrix[5] == 1.0, (
            f"{name} must NOT flip the mip-downsample pass: got y scale "
            f"{matrix[5]!r}. A flip here inverts every generated level "
            "relative to its source, so levels alternate by parity and "
            "trilinear minification blends upright with flipped content "
            "(plan-tile-policy-reliability-2026-10-24)"
        )
        assert matrix == _IDENTITY, f"{name} correction must be identity, got {matrix!r}"


def test_vulkan_keeps_the_flip():
    """Vulkan reports y-down in framebuffer, yet needs the flip (measured).

    Red if the gate goes back to ``isYUpInFramebuffer()``: Vulkan reports
    False there, which would drop the flip and flip every tile on Linux.
    """
    matrix = downsample_corr_matrix(_Rhi(QRhi.Implementation.Vulkan))
    assert matrix[5] == -1.0, (
        "Vulkan must keep the mip-downsample Y flip: got y scale "
        f"{matrix[5]!r}. isYUpInFramebuffer() is False on Vulkan too, so it "
        "cannot be the gate (see docs/dev/rendering/qrhi-gotchas.md)"
    )


def test_opengl_keeps_the_flip():
    """OpenGL/GLES2: y-up framebuffer, flip required (the original behaviour)."""
    matrix = downsample_corr_matrix(_Rhi(QRhi.Implementation.OpenGLES2))
    assert matrix[5] == -1.0, (
        f"OpenGL must keep the mip-downsample Y flip, got y scale {matrix[5]!r}"
    )


def test_metal_keeps_the_flip():
    """Metal is y-up like OpenGL and was never in the no-flip family."""
    matrix = downsample_corr_matrix(_Rhi(QRhi.Implementation.Metal))
    assert matrix[5] == -1.0


def test_missing_backend_query_keeps_the_flip():
    """Unknown backend: never guess a flip away."""
    matrix = downsample_corr_matrix(_RhiWithoutQuery())
    assert matrix[5] == -1.0, (
        "a backend object without backend() must keep the flip, got y scale "
        f"{matrix[5]!r}"
    )


def test_d3d_enum_members_exist():
    """Pin the enum: if a Qt update renames them, this fails loudly instead of
    silently re-enabling the flip on D3D (which is what shipped the bug)."""
    for name in ("D3D11", "D3D12"):
        assert hasattr(QRhi.Implementation, name), (
            f"QRhi.Implementation.{name} is gone: the mip-cascade no-flip gate "
            "would silently default to flipping on D3D (the 2026-10-24 bug)"
        )


@pytest.mark.parametrize(
    "backend_name",
    ["D3D11", "D3D12", "Vulkan", "OpenGLES2", "Metal"],
)
def test_correction_is_diagonal_for_every_backend(backend_name):
    """Diagonal for every backend -- the uniform's row/column order cannot matter."""
    backend = getattr(QRhi.Implementation, backend_name, None)
    if backend is None:
        pytest.skip(f"backend {backend_name} not in this Qt build")
    matrix = downsample_corr_matrix(_Rhi(backend))
    assert len(matrix) == 16
    for index in (1, 2, 3, 4, 6, 7, 8, 9, 11, 12, 13, 14):
        assert matrix[index] == 0.0, (
            f"correction matrix must be diagonal (index {index} = "
            f"{matrix[index]!r}, backend {backend_name})"
        )
    assert (matrix[0], matrix[10], matrix[15]) == (1.0, 1.0, 1.0)
