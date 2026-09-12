from __future__ import annotations


def pick_first_real(*candidates):
    """Picks the first non-``None`` candidate that isn't a ``TiledPixelStore``.

    Single canonical implementation of the "which image do we actually show"
    fallback chain -- see docs/dev/DISPLAY_IMAGE_PIPELINE.md. Any role that
    ends up rendered as a whole-image GPU texture or QPixmap must never
    receive a memmap-backed full-res store; callers pass their own ordered
    list of candidates (display cache, scaled-display cache, live unified
    image, preview/original fallbacks) and get back the first one that's safe
    to hand to a renderer.
    """
    from shared.image_processing.tiled_pixel_store import TiledPixelStore

    for candidate in candidates:
        if candidate is not None and not isinstance(candidate, TiledPixelStore):
            return candidate
    return None
