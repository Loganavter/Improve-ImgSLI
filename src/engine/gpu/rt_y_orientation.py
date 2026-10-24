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

Two legacy sites predate this helper and decide a one-bit Y question instead
of a correction matrix. They are named cases here for the same reason the
three above are: the bug class is a local predicate reading one query, and
these two read ``isYUpInFramebuffer()`` for a *different* job than
``SAMPLED_RT`` does.

``WIDGET_TEXTURE``
    A **copy** out of a widget's own backing texture (``colorTexture()``) that
    a later pass in the same frame samples -- the liquid-glass backdrop crop
    in ``glass_panel``. Use ``widget_texture_needs_y_flip(rhi)``. This is NOT
    ``SAMPLED_RT``: a target this code renders into needs the stronger
    predicate, while a copy of an already-populated texture only depends on
    the row order that backend stores it in. Vulkan answers
    ``isYUpInFramebuffer()`` like D3D11 and (measured on the dev host,
    2026-08-17) stores ``colorTexture()`` top-down, so a Vulkan copy must NOT
    flip. Do not use this for a pass's own render target (that is
    ``SAMPLED_RT``), and do not use ``sampled_rt_needs_y_flip`` for a copy.

``COMPOSITED_SCISSOR``
    A **scissor rect** in device px inside a composited widget's own
    framebuffer (guides, capture overlay, magnifier tiles, divider). Use
    ``composited_scissor_needs_y_flip(rhi, never_shown=...)``. Qt's
    compositing step absorbs the convention mismatch for a *shown* widget, so
    only the framebuffer-origin query applies there; a widget rendered with
    ``WA_DontShowOnScreen`` (``grabFramebuffer()``-only canvases such as the
    GPU export/preview canvas) skips that step, so the raw scissor Y flips
    regardless of what the query reports. This is one integer rect, not a
    projection -- a pass that needs clip-space correction uses
    ``composited_clip_correction``.

================  =================  =================  ===================
backend           isYUpInFramebuf   WIDGET_TEXTURE     COMPOSITED_SCISSOR
================  =================  =================  ===================
OpenGL / GLES2    True               flip               flip
Vulkan            False              no flip            no flip
D3D11             False              no flip            no flip
Metal (predicted) False              no flip            no flip
================  =================  =================  ===================

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

Self-calibration (``IMGSLI_RT_ORIENTATION_PROBE=1``)
    The derived rule above is a PREDICTION on Metal/D3D12 and could be
    invalidated by a future Qt change. When the flag is on, the mip cascade
    renders one tiny asymmetric source through its REAL downsample pipeline
    into its REAL scratch target, reads the result back, and reports the
    flip the target actually needed via ``record_sampled_rt_orientation``.
    That observation is kept per RHI object (same lifetime pattern as
    ``_traced`` below) and WINS over the derived rule for the rest of the
    session; a disagreement is logged at WARNING with backend, predicted and
    observed flip plus the one-line fix. An unreadable readback records
    nothing (``observed_flip=None``) and the derived rule stays in force.
    With the flag off (the default) nothing is probed, read back or logged --
    the predicate is the whole behaviour again.

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

#: Env-gated self-calibration of the SAMPLED_RT rule: when on, a pass may
#: render one tiny known-asymmetric source through its real pipeline and
#: report the flip the target actually needed. Read once at import, exactly
#: like ``_TRACE_ENABLED``; off (the default) means no probe, no readback, no
#: extra log line anywhere.
_PROBE_ENABLED = os.environ.get(
    "IMGSLI_RT_ORIENTATION_PROBE", ""
).strip().lower() not in ("", "0", "false", "no", "off")

#: Observed flips, keyed on ``id(rhi)`` -- one RHI object is one session, so
#: the same lifetime pattern as ``_traced``. A recorded value WINS over the
#: predicate derived from the two documented QRhi properties; it is never a
#: process-wide flip (a second RHI keeps its own answer).
_observed_flips: dict[int, bool] = {}

#: RHIs whose single calibration probe has already been claimed (or attempted).
_probe_claimed: set[int] = set()

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


def _backend_name(rhi) -> str:
    """Backend label for probe logs; never raises on a stub RHI."""
    try:
        return str(rhi.backendName() or "")
    except Exception:
        return type(rhi).__name__


def _derived_needs_y_flip(rhi) -> bool:
    """The predicate from the two documented QRhi properties, no overrides.

    A backend that cannot answer either query keeps the flip (never guess a
    flip away, and never silently drop the behaviour that shipped for a
    year).
    """
    try:
        y_up_framebuffer = bool(rhi.isYUpInFramebuffer())
        y_up_ndc = bool(rhi.isYUpInNDC())
    except (AttributeError, RuntimeError):
        return True
    return y_up_framebuffer or not y_up_ndc


def sampled_rt_orientation_probe_enabled() -> bool:
    """Whether the env-gated self-calibration probe may run.

    Read once at import from ``IMGSLI_RT_ORIENTATION_PROBE``. Callers ask at
    use time so a test (or a future interactive switch) can flip the module
    flag without reimporting.
    """
    return _PROBE_ENABLED


def claim_sampled_rt_orientation_probe(rhi) -> bool:
    """Claim the ONE calibration probe allowed for this RHI; True on the first.

    A pass must call this before rendering its probe: it keeps a probe to one
    per ``(rhi, session)`` so a per-frame cascade cannot keep rendering the
    calibration source. Claiming without recording is deliberate -- an
    unreadable readback also consumes the attempt (retrying every frame would
    only add GPU work, never a different answer).
    """
    key = id(rhi)
    if key in _probe_claimed:
        return False
    _probe_claimed.add(key)
    return True


def record_sampled_rt_orientation(rhi, *, observed_flip: bool | None) -> None:
    """Record the SAMPLED_RT flip a real probe observed for ``rhi``.

    ``True``/``False`` = the target really needed (or did not need) the flip, as read
    back from the probe. It overrides the derived predicate for this RHI for
    the rest of the session, and a disagreement is logged at WARNING (always,
    not only under ``IMGSLI_RT_ORIENTATION_TRACE``) with the backend, the
    predicted and the observed flip and the one-line fix.

    ``None`` = the readback was unreadable/empty: record nothing, keep the
    derived rule, and log at INFO once so the field log shows the probe ran
    without pretending it measured anything.
    """
    derived = _derived_needs_y_flip(rhi)
    backend = _backend_name(rhi)
    if observed_flip is None:
        logger.info(
            "[rt-y] orientation probe unreadable: backend=%s predicted_flip=%s "
            "-> keeping the derived rule (engine/gpu/rt_y_orientation.py)",
            backend,
            derived,
        )
        return
    observed = bool(observed_flip)
    _observed_flips[id(rhi)] = observed
    if observed == derived:
        logger.info(
            "[rt-y] orientation probe agrees: backend=%s sampled-RT flip=%s "
            "(engine/gpu/rt_y_orientation.py)",
            backend,
            observed,
        )
        return
    logger.warning(
        "[rt-y] SAMPLED-RT orientation DISAGREES with the derived rule: "
        "backend=%s predicted_flip=%s observed_flip=%s -- fix: change the "
        "predicate/table in engine/gpu/rt_y_orientation.py to flip=%s for this "
        "backend (a probe override is active for this session; without it every "
        "generated mip level is stored with the wrong orientation)",
        backend,
        derived,
        observed,
        observed,
    )


def sampled_rt_needs_y_flip(rhi) -> bool:
    """Whether a pass into a SAMPLED offscreen target must flip Y.

    A flip observed by the calibration probe (``record_sampled_rt_orientation``)
    wins for that RHI. Otherwise derived from the two documented conventions
    (see module docstring):

        needs_flip = isYUpInFramebuffer() or not isYUpInNDC()

    OpenGL -> flip, Vulkan -> flip, D3D11/12 and Metal -> no flip. A backend
    that cannot answer either query keeps the flip (never guess a flip away,
    and never silently drop the behaviour that shipped for a year).
    """
    recorded = _observed_flips.get(id(rhi))
    if recorded is not None:
        return recorded
    return _derived_needs_y_flip(rhi)


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


def widget_texture_needs_y_flip(rhi) -> bool:
    """Whether a COPY of a widget's own ``colorTexture()`` must flip source Y.

    ``WIDGET_TEXTURE`` case (see module docstring): the copy source is an
    already-populated texture, so only its row order matters -- flip iff the
    framebuffer origin is bottom-left (``isYUpInFramebuffer()``). This is NOT
    ``sampled_rt_needs_y_flip``: that predicate also flips when clip space is
    y-down (Vulkan), which is right for a target *this* module renders into
    and wrong for a copy out of a texture the backend already stored. Vulkan
    answers this query like D3D11 and must not flip. Do not use it for a
    pass's own render target, and do not use the SAMPLED_RT predicate here.

    Unqueryable (missing attribute, ``AttributeError``/``RuntimeError`` from
    the query) -> ``False``: a copy of a foreign texture cannot guess a flip,
    and "no flip" is the behaviour ``glass_panel`` shipped with on every
    backend it was measured on. Fail-safe means "keep the shipped pixels",
    not "invent a mirror".
    """
    try:
        return bool(rhi.isYUpInFramebuffer())
    except (AttributeError, RuntimeError):
        return False


def composited_scissor_needs_y_flip(rhi, *, never_shown: bool) -> bool:
    """Whether a scissor rect in a composited widget must flip framebuffer Y.

    ``COMPOSITED_SCISSOR`` case (see module docstring): Qt's compositing step
    absorbs the convention mismatch for a *shown* widget, so only
    ``isYUpInFramebuffer()`` applies there. A widget rendered with
    ``WA_DontShowOnScreen`` (``grabFramebuffer()``-only canvases such as the
    GPU export/preview canvas) skips that step, so the raw scissor Y must be
    flipped regardless of the query. Not a projection correction -- use
    ``composited_clip_correction`` for clip space.

    Unqueryable (missing attribute, ``AttributeError``/``RuntimeError``) ->
    ``never_shown``: a never-shown widget has nothing that could absorb the
    mismatch, so the historical raw-flip behaviour is the safe answer there;
    a shown one keeps the composited behaviour it has always had.
    """
    try:
        y_up = bool(rhi.isYUpInFramebuffer())
    except (AttributeError, RuntimeError):
        return bool(never_shown)
    return y_up or bool(never_shown)
