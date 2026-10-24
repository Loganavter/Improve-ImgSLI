"""Single source of truth for Y-orientation corrections in QRhi passes.

The 2026-10-24 incident this module exists for: `mip_cascade` hardcoded a Y
flip for a pass that renders into an offscreen texture and samples it. It was
right on OpenGL/Vulkan and wrong on D3D11, and the artifact (flipped/partial
tiles below 1:1) was blamed on the tile pipeline for a whole diagnosis cycle.
A second attempt gated the flip on ``rhi.isYUpInFramebuffer()`` and flipped
every tile on **Vulkan** within the hour. Both failures came from the same
mistake: a pass deciding a convention from a comment, or from a single query
that does not actually distinguish the cases.

There are exactly THREE cases. Pick the one that matches what happens to the
pixels, never what backend you happen to be on:

``COMPOSITED``
    The pass writes into the widget's own render target, which a
    ``QRhiWidget`` then composites on screen. Use
    ``composited_clip_correction(rhi)`` -- it returns
    ``rhi.clipSpaceCorrMatrix()`` verbatim. Do not hand-roll anything: the
    compositing step is what absorbs the remaining convention mismatch, and
    adding a flip on top inverts the image on backends where the correction
    already covers it.

``SAMPLED_RT``
    The pass writes into an offscreen texture that is later **sampled**
    (mip cascade, scratch/downsample targets, export readback canvases). No
    compositing step cancels anything, so the correction is decided by the
    backend FAMILY -- ``sampled_rt_correction(rhi)``, table below. This is the
    case that bit us; ``isYUpInFramebuffer()`` is NOT a valid gate for it
    because Vulkan answers like D3D and still needs the flip.

``NONE``
    Nothing to correct (no render target involved).

Measured evidence (``QRhiWidget.setApi(...)`` on the dev host, 2026-10-24):

=======================  ===================  ==========================  =================
backend                  isYUpInFramebuffer   clipSpaceCorrMatrix         SAMPLED_RT flip
=======================  ===================  ==========================  =================
OpenGL / GLES2           True                 identity                    yes
Vulkan                   False                Y flip + 0..1 depth scale   yes
D3D11                    --                   --                          no (dump-proven)
=======================  ===================  ==========================  =================

D3D12 is in the same family as D3D11 by QRhi's own convention split; Metal is
y-up like OpenGL. Those two are the untested cells of the table -- treat them
as the family default (D3D: no flip, Metal: flip) and validate before trusting
a new backend either way.

Contracts pinning this module: ``tests/contracts/test_rt_y_orientation.py``
(single-source: nothing else in ``src/`` may build a flip literal or call the
two queries outside the allowlist below) and
``tests/render/test_mip_cascade_y_parity.py`` (the cascade's own matrix).
"""

from __future__ import annotations

from PySide6.QtGui import QRhi

#: Backend family that needs NO Y correction for a sampled render target.
_D3D_BACKENDS = frozenset(
    getattr(QRhi.Implementation, name)
    for name in ("D3D11", "D3D12")
    if hasattr(QRhi.Implementation, name)
)

IDENTITY_MATRIX: tuple[float, ...] = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)

Y_FLIP_MATRIX: tuple[float, ...] = (
    1.0, 0.0, 0.0, 0.0,
    0.0, -1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)


def is_d3d_backend(rhi) -> bool:
    """True only for a D3D-family backend; False for everything unknown."""
    try:
        backend = rhi.backend()
    except (AttributeError, RuntimeError):
        return False
    return backend in _D3D_BACKENDS


def sampled_rt_needs_y_flip(rhi) -> bool:
    """Whether a pass into a SAMPLED offscreen target must flip Y.

    Flip everywhere except the D3D family -- the one family measured to need
    none. An unqueryable backend keeps the flip (never guess a flip away).
    """
    return not is_d3d_backend(rhi)


def sampled_rt_correction(rhi) -> tuple[float, ...]:
    """Row-major ``mat4`` for a pass whose target is later sampled.

    Diagonal, so row-major vs column-major storage does not matter.
    """
    return IDENTITY_MATRIX if is_d3d_backend(rhi) else Y_FLIP_MATRIX


def composited_clip_matrix(rhi):
    """``rhi.clipSpaceCorrMatrix()`` as the QRhi object, for products.

    Some passes multiply it with their own projection before packing (e.g. an
    ortho * corr product for pixel-space quads); they need the matrix, not a
    float tuple.
    """
    return rhi.clipSpaceCorrMatrix()


def composited_clip_correction(rhi) -> tuple[float, ...]:
    """Row-major ``mat4`` for a pass composited on screen by its QRhiWidget.

    This is ``rhi.clipSpaceCorrMatrix()`` verbatim -- the widget's own
    compositing absorbs the remaining convention mismatch, so no extra flip.
    """
    return tuple(float(value) for value in composited_clip_matrix(rhi).data())
