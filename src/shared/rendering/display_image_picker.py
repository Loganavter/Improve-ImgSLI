from __future__ import annotations


def pick_first_real(*candidates):
    """Picks the first non-``None`` candidate that isn't a ``LazyPixelSource``.

    Single canonical implementation of the "which image do we actually show"
    fallback chain -- see docs/dev/DISPLAY_IMAGE_PIPELINE.md. Any role that
    ends up rendered as a whole-image GPU texture or QPixmap must never
    receive a lazy (memmap-backed, >PHASE3_LAZY_THRESHOLD_PX) source; callers
    pass their own ordered list of candidates (display cache, scaled-display
    cache, live unified image, preview/original fallbacks) and get back the
    first one that's safe to hand to a renderer.
    """
    from shared.image_processing.lazy_pixel_source import LazyPixelSource

    for candidate in candidates:
        if candidate is not None and not isinstance(candidate, LazyPixelSource):
            return candidate
    return None
