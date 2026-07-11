from __future__ import annotations

import math

from PySide6.QtCore import QPointF

from tabs.image_compare.canvas.features.magnifier.scene.objects import MagnifierSceneObject


def _normalize_arc_deg(start_deg: float, end_deg: float) -> list[tuple[float, float]]:
    start = start_deg % 360.0
    end = end_deg % 360.0
    if math.isclose(start, end, abs_tol=1e-9):
        return [(0.0, 360.0)]
    if start <= end:
        return [(start, end)]
    return [(start, 360.0), (0.0, end)]


def _merge_arc_ranges(ranges: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not ranges:
        return []
    ordered = sorted(ranges, key=lambda item: item[0])
    merged: list[list[float]] = [[ordered[0][0], ordered[0][1]]]
    for start, end in ordered[1:]:
        last = merged[-1]
        if start <= last[1] + 1e-6:
            last[1] = max(last[1], end)
        else:
            merged.append([start, end])
    if len(merged) >= 2 and merged[0][0] <= 1e-6 and merged[-1][1] >= 360.0 - 1e-6:
        wrapped = [merged[-1][0] - 360.0, merged[0][1]]
        middle = merged[1:-1]
        merged = [wrapped] + middle
    return [(start, end) for start, end in merged]


def compute_occluded_capture_arcs(
    all_magnifiers: list[MagnifierSceneObject],
    visible_magnifiers: list[MagnifierSceneObject],
    active_object_id: str | None,
) -> list[tuple[QPointF, float, float, float, bool]]:
    arcs: list[tuple[QPointF, float, float, float, bool]] = []

    for obj in visible_magnifiers:
        center = getattr(obj, "capture_center", None)
        radius = float(getattr(obj, "capture_radius", 0.0) or 0.0)
        if center is None or radius <= 0:
            continue
        ranges: list[tuple[float, float]] = []
        cx = float(center.x)
        cy = float(center.y)
        for other in visible_magnifiers:
            for circle in getattr(other, "circles", ()) or ():
                if circle.center is None or circle.radius <= 0 or not circle.visible:
                    continue
                ox = float(circle.center.x)
                oy = float(circle.center.y)
                oradius = float(circle.radius)
                dx = ox - cx
                dy = oy - cy
                distance = math.hypot(dx, dy)
                if distance <= 1e-6:
                    if oradius >= radius - 1e-6:
                        ranges = [(0.0, 360.0)]
                        break
                    continue
                if distance >= radius + oradius - 1e-6:
                    continue
                if distance + radius <= oradius + 1e-6:
                    ranges = [(0.0, 360.0)]
                    break
                cosine = (distance * distance + radius * radius - oradius * oradius) / (
                    2.0 * distance * radius
                )
                cosine = max(-1.0, min(1.0, cosine))
                half_angle = math.degrees(math.acos(cosine))

                center_angle = math.degrees(math.atan2(-dy, dx))
                ranges.extend(
                    _normalize_arc_deg(
                        center_angle - half_angle, center_angle + half_angle
                    )
                )
            if ranges == [(0.0, 360.0)]:
                break
        for start_deg, end_deg in _merge_arc_ranges(ranges):
            span_deg = end_deg - start_deg
            if span_deg <= 0.25:
                continue
            arcs.append(
                (
                    QPointF(cx, cy),
                    radius,
                    start_deg,
                    span_deg,
                    obj.id == active_object_id,
                )
            )
    return arcs
