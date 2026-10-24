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
    compositing step cancels anything, so the correction is derived from the
    two documented QRhi conventions -- ``sampled_rt_correction(rhi)``, rule and
    measured table below. This is the case that bit us; a single query is NOT a
    valid gate for it, because Vulkan answers ``isYUpInFramebuffer()`` like D3D
    and still needs the flip.

``NONE``
    Nothing to correct (no render target involved).

The rule is derived from two DOCUMENTED QRhi properties, not from a
per-family list:

* "framebuffers use an origin-at-top-left system everywhere except OpenGL"
  (Qt docs, RHI under QML) -> ``isYUpInFramebuffer()`` is True on OpenGL and
  False elsewhere;
* clip-space Y points down only on Vulkan -> ``isYUpInNDC()`` is False for
  Vulkan, True everywhere else (Qt docs: "in practice this is false for
  Vulkan only").

A pass that stores a level for later SAMPLING needs a flip when either the
framebuffer origin is bottom-left (OpenGL) or clip space is y-down (Vulkan):

    needs_flip = isYUpInFramebuffer() or not isYUpInNDC()

Measured against the dev host (``QRhiWidget.setApi(...)``, 2026-10-24) and the
D3D11 host's readback dump:

=======================  ================  ===========  =======================  ==========
backend                  isYUpInFramebuf   isYUpInNDC   predicate                measured
=======================  ================  ===========  =======================  ==========
OpenGL / GLES2           True              True         flip                     flip
Vulkan                   False             False        flip                     flip
D3D11                    False             True         no flip                  no flip
Metal (predicted)        False             True         no flip                  untested
D3D12 (predicted)        False             True         no flip                  untested
=======================  ================  ===========  =======================  ==========

The two untested cells are why the predicate still fails safe: a backend that
cannot answer either query keeps the flip (the historical behaviour that
shipped for a year), and ``IMGSLI_RT_ORIENTATION_TRACE=1`` logs the backend and
the predicate once per process so a wrong prediction is visible in the field
instead of silent. The earlier fixed family list guessed Metal wrong; a rule
that reads the two documented properties does not need to guess.

Contracts pinning this module: ``tests/contracts/test_rt_y_orientation.py``
(single-source: nothing else in ``src/`` may build a flip literal or call the
two queries outside the allowlist below) and
``tests/render/test_mip_cascade_y_parity.py`` (the cascade's own matrix).
"""

from __future__ import annotations

import logging
import os

from PySide6.QtGui import QRhi

logger = logging.getLogger("ImproveImgSLI")

#: Log the backend + the derived predicate once per process. A wrong
#: prediction on an untested backend then shows up in the field log instead of
#: as a silent flipped canvas.
_TRACE_ENABLED = os.environ.get("IMGSLI_RT_ORIENTATION_TRACE", "").strip().lower() not in (
    "",
    "0",
    "false",
    "no",
    "off",
)
_traced: set[int] = set()

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


def sampled_rt_needs_y_flip(rhi) -> bool:
    """Whether a pass into a SAMPLED offscreen target must flip Y.

    Derived from the two documented conventions (see module docstring):

        needs_flip = isYUpInFramebuffer() or not isYUpInNDC()

    OpenGL -> flip, Vulkan -> flip, D3D11/12 and Metal -> no flip. A backend
    that cannot answer either query keeps the flip (never guess a flip away,
    and never silently drop the behaviour that shipped for a year).
    """
    try:
        y_up_framebuffer = bool(rhi.isYUpInFramebuffer())
        y_up_ndc = bool(rhi.isYUpInNDC())
    except (AttributeError, RuntimeError):
        return True
    return y_up_framebuffer or not y_up_ndc


def _trace_once(rhi, needs_flip: bool) -> None:
    if not _TRACE_ENABLED or id(rhi) in _traced:
        return
    _traced.add(id(rhi))
    try:
        backend = rhi.backend()
        y_up_fb = bool(rhi.isYUpInFramebuffer())
        y_up_ndc = bool(rhi.isYUpInNDC())
    except (AttributeError, RuntimeError):
        backend, y_up_fb, y_up_ndc = "<unqueryable>", None, None
    logger.info(
        "[rt-y] backend=%s isYUpInFramebuffer=%s isYUpInNDC=%s -> "
        "sampled-RT flip=%s (engine/gpu/rt_y_orientation.py)",
        backend,
        y_up_fb,
        y_up_ndc,
        needs_flip,
    )


def sampled_rt_correction(rhi) -> tuple[float, ...]:
    """Row-major ``mat4`` for a pass whose target is later sampled.

    Diagonal, so row-major vs column-major storage does not matter.
    """
    needs_flip = sampled_rt_needs_y_flip(rhi)
    _trace_once(rhi, needs_flip)
    return Y_FLIP_MATRIX if needs_flip else IDENTITY_MATRIX


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
