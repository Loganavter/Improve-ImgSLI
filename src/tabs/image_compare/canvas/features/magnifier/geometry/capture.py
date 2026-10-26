"""ONE owner for the loupe's capture geometry (the sampled area).

Two independent user controls, no hidden coupling (owner decision 2026-10-26,
second revision):

* **Magnifier size** (``size_relative``) — only the drawn disk. Moving it must
  NOT change what is sampled.
* **Capture size** (``capture_size_relative``) — only the sampled area (the pink
  ring). Moving it changes the loupe's ratio, which is the point of the control.

The magnification is therefore *derived and reported*, never enforced — it is
``drawn_disk_radius_widget / capture_radius_source``. An earlier revision made it
an invariant by deriving the capture radius from the disk, which tied the two
sliders together and made the ring chase the size slider; that is what this
module undoes.

``display_scale`` is used ONLY to report the resulting magnification (screen px
per source px), which is what the eye judges: a loupe whose disk is drawn at the
canvas' letterboxed scale and whose capture is a percentage of the image can put
less than one screen pixel on one source pixel for a big image in a small window.
Reporting it keeps the ratio honest instead of hiding it in the geometry.

This module used to be duplicated: the renderer (``geometry/layout_plan.py``) and
the scene graph (``scene/build.py`` — hit-testing, guides, ``get_canvas_scene``)
recomputed the capture radius independently, and with a derived radius they
silently disagreed (measured: scene 5.54 pixmap px vs plan 11.44 canvas px). Both
now resolve here.
"""

from __future__ import annotations

import math

from tabs.image_compare.canvas.features.magnifier.constants import (
    DEFAULT_CAPTURE_SIZE_RELATIVE,
)


def resolve_magnifier_capture_radius(
    *,
    size_relative: float,
    capture_size_relative: float,
    pix_w: float,
    pix_h: float,
    display_scale: float = 1.0,
) -> tuple[float, float]:
    """Return ``(capture_radius_canvas_px, magnification)``.

    ``pix_w``/``pix_h`` are the content size in canvas px (the space the loupe is
    authored in); ``display_scale`` is canvas px -> widget px
    (``runtime_state._content_sr``).

    The returned radius depends on ``capture_size_relative`` ONLY — ``size_relative``
    is used solely to report the resulting magnification, so the two sliders stay
    independent by construction.
    """
    short_edge = max(1.0, min(float(pix_w), float(pix_h)))
    capture_rel = float(capture_size_relative or 0.0) or DEFAULT_CAPTURE_SIZE_RELATIVE
    # The capture control is a percentage OF THE IMAGE, in source px — that is
    # what its label says and what the ring draws. No display-scale factor here:
    # the window size must not change what a "10%" capture means.
    capture_radius = (capture_rel * short_edge) / 2.0
    target_max = math.sqrt(max(1.0, float(pix_w)) * max(1.0, float(pix_h)))
    disk_radius_widget = (float(size_relative) * target_max) / 2.0 * max(
        1e-6, float(display_scale or 1.0)
    )
    magnification = (
        disk_radius_widget / capture_radius if capture_radius > 1e-9 else 1.0
    )
    return capture_radius, magnification


def capture_size_relative_for_radius(radius: float, pix_w: float, pix_h: float) -> float:
    """The relative size the position clamp expects for a resolved radius."""
    return (2.0 * float(radius)) / float(max(1, min(int(pix_w), int(pix_h))))
