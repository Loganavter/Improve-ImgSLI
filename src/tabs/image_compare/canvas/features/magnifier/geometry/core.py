from __future__ import annotations

import math

from domain.types import Rect


def clamp_capture_position(
    rel_x: float,
    rel_y: float,
    pix_w: int,
    pix_h: int,
    capture_size_relative: float,
):
    if pix_w <= 0 or pix_h <= 0:
        return rel_x, rel_y
    ref_dim = math.sqrt(float(pix_w) * float(pix_h))
    capture_size_px = capture_size_relative * ref_dim
    radius_rel_x = (capture_size_px / 2.0) / pix_w if pix_w > 0 else 0.0
    radius_rel_y = (capture_size_px / 2.0) / pix_h if pix_h > 0 else 0.0
    return (
        max(radius_rel_x, min(rel_x, 1.0 - radius_rel_x)),
        max(radius_rel_y, min(rel_y, 1.0 - radius_rel_y)),
    )


def clamp_capture_overlay_geometry(
    *,
    bounds: Rect,
    center_x: float,
    center_y: float,
    radius: float,
):
    if bounds.w <= 0 or bounds.h <= 0 or radius <= 0:
        return center_x, center_y, max(0.0, radius)

    left = float(bounds.x)
    top = float(bounds.y)
    right = float(bounds.x + bounds.w)
    bottom = float(bounds.y + bounds.h)

    max_radius_x = max(0.0, (right - left) / 2.0)
    max_radius_y = max(0.0, (bottom - top) / 2.0)
    clamped_radius = min(radius, max_radius_x, max_radius_y)

    clamped_x = min(max(center_x, left + clamped_radius), right - clamped_radius)
    clamped_y = min(max(center_y, top + clamped_radius), bottom - clamped_radius)
    return clamped_x, clamped_y, clamped_radius
