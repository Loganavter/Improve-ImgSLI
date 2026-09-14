from __future__ import annotations

from shared.image_processing.pyramid_registry import pyramid_for
from shared.image_processing.tiled_pixel_store import TiledPixelStore


def pick_first_real(*candidates):
    """Picks the first non-``None`` candidate.

    Single canonical implementation of the "which image do we actually show"
    fallback chain -- see docs/dev/rendering/display-image-pipeline.md.
    Callers pass their own ordered list of candidates (live unified image,
    preview/original fallbacks).
    """
    for candidate in candidates:
        if candidate is not None:
            return candidate
    return None


def pick_display_image(*candidates):
    """``pick_first_real`` for the display (stored) role.

    A ``TiledPixelStore`` is only eligible once its mipmap pyramid is
    complete: without a coarse level the canvas would have to crop+upload
    raw level-0 tiles (gigabytes for a 20k pair) just to draw an overview.
    Until the pyramid builder catches up, the preview-tier candidate stays
    on screen -- the same UX the old display cache gave while it was being
    built. If every candidate is a not-yet-ready store (no preview to fall
    back to), the first non-None one is returned anyway: a slow first frame
    beats a blank canvas.
    """
    for candidate in candidates:
        if candidate is None:
            continue
        if isinstance(candidate, TiledPixelStore):
            pyramid = pyramid_for(candidate)
            if pyramid is None or not pyramid.is_complete():
                continue
        return candidate
    return pick_first_real(*candidates)
