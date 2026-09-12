from __future__ import annotations

import math

from core.constants import AppConstants
from domain.types import Point

def resolve_axis_direction(
    keys,
    last_key,
    *,
    negative_key: int,
    positive_key: int,
) -> int:
    negative_down = negative_key in keys
    positive_down = positive_key in keys
    if negative_down and positive_down:
        if last_key == negative_key:
            return -1
        if last_key == positive_key:
            return 1
        return 0
    if positive_down:
        return 1
    if negative_down:
        return -1
    return 0

def damp(current, target, smoothing: float, dt: float):
    return target + (current - target) * math.exp(-smoothing * dt)

def damp_vector(current: Point, target: Point, smoothing: float, dt: float) -> Point:
    return Point(
        damp(current.x, target.x, smoothing, dt),
        damp(current.y, target.y, smoothing, dt),
    )

def is_close(p1: Point, p2: Point, tol: float | None = None) -> bool:
    if tol is None:
        tol = AppConstants.LERP_STOP_THRESHOLD
    return math.isclose(p1.x, p2.x, abs_tol=tol) and math.isclose(
        p1.y,
        p2.y,
        abs_tol=tol,
    )

