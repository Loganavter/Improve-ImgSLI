"""Mip-cascade Y correction is per-backend, never unconditional.

Why this exists (plan-tile-policy-reliability-2026-10-24, P0 verdict
2026-10-24): the cascade used to write an UNCONDITIONAL Y-flip into its
downsample vertex stage. On OpenGL that is required; on D3D11 it inverted
every generated level relative to its source, so the chain alternated by
level parity (odd levels upside-down). The tile sampler is trilinear, so any
zoom below 1:1 blended upright mip0 with flipped mip1 -- the "bands showing
another tile's content / a tile fills only a third of its place" artifact on
the D3D11 host, absent at >= 1:1 (mip0 only) and absent in the magnifier
(near 1:1).

Measured from the D3D11 host's ``IMGSLI_TILE_DUMP`` mip readbacks before the
fix: each consecutive level pair matched a vertical flip at mean|delta|
2.4-13, identity at 42-59 -- i.e. flip parity exactly opposite to the code's
intent.

The fix asks the backend (``QRhi.isYUpInFramebuffer()``), matching the
existing precedent in ``engine/gpu/glass_panel.py``. These tests pin the
matrix per backend; the live proof is the readback parity on the D3D11 host.
"""

from __future__ import annotations

from engine.gpu.mip_cascade import downsample_corr_matrix

_IDENTITY = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)


class _Rhi:
    def __init__(self, y_up_in_framebuffer: bool) -> None:
        self._y_up = y_up_in_framebuffer

    def isYUpInFramebuffer(self) -> bool:
        return self._y_up


class _RhiWithoutQuery:
    """A backend that does not expose the query (older/unknown QRhi)."""


def test_d3d11_y_down_must_not_flip():
    """D3D11 reports y-down: applying the flip re-flips every level.

    Red before the fix: the matrix was the flip on every backend, so the
    chain alternated by parity and the trilinear sampler blended upright
    with upside-down content below 1:1.
    """
    matrix = downsample_corr_matrix(_Rhi(False))
    assert matrix[5] == 1.0, (
        "mip-cascade vertex stage must NOT flip on a y-down framebuffer "
        f"(D3D11): got y scale {matrix[5]!r}. A flip here inverts every "
        "generated level relative to its source, so levels alternate by "
        "parity and trilinear minification blends upright with flipped "
        "content (plan-tile-policy-reliability-2026-10-24)"
    )
    assert matrix == _IDENTITY, (
        f"y-down correction must be the identity matrix, got {matrix!r}"
    )


def test_opengl_y_up_keeps_the_flip():
    """OpenGL reports y-up: the flip is required (the pre-2026-10-24 fix)."""
    matrix = downsample_corr_matrix(_Rhi(True))
    assert matrix[5] == -1.0, (
        "mip-cascade vertex stage must flip on a y-up framebuffer "
        f"(OpenGL): got y scale {matrix[5]!r}"
    )


def test_missing_query_keeps_opengl_behaviour():
    """No query available: keep the OpenGL-proven flip, never guess silently."""
    matrix = downsample_corr_matrix(_RhiWithoutQuery())
    assert matrix[5] == -1.0, (
        "a backend without isYUpInFramebuffer() must keep the OpenGL-proven "
        f"flip, got y scale {matrix[5]!r}"
    )


def test_correction_is_diagonal_for_every_backend():
    """Both variants are diagonal -- the uniform's row/column order cannot matter."""
    for y_up in (True, False):
        matrix = downsample_corr_matrix(_Rhi(y_up))
        assert len(matrix) == 16
        for index in (1, 2, 3, 4, 6, 7, 8, 9, 11, 12, 13, 14):
            assert matrix[index] == 0.0, (
                f"correction matrix must be diagonal (index {index} = "
                f"{matrix[index]!r}, y_up={y_up})"
            )
        assert (matrix[0], matrix[10], matrix[15]) == (1.0, 1.0, 1.0)
