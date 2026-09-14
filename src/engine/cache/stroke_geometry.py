"""Shared helper for annotation passes that stroke a circle/arc whose fill
radius is already clamped to touch some bound (e.g. an image edge) exactly.

A centered stroke extends half its own line width outward from the fill
radius it's drawn on, so once that radius is at its clamped maximum, the
stroke's visible outer edge overshoots the bound by that same half-width.
Shrinking the (already zoom/scale-scaled, screen-px) radius passed to the
shader by that half-width cancels the overshoot exactly, without needing
any upstream margin baked into the geometry clamp itself — which must stay
zoom-independent (the fill radius is computed once in content space and
must not shift just because the viewport's zoom changed).
"""

from __future__ import annotations


def shrink_screen_radius_for_stroke(screen_radius: float, stroke_width_px: float) -> float:
    half_width = max(0.5, float(stroke_width_px) * 0.5)
    return max(0.0, float(screen_radius) - half_width)
