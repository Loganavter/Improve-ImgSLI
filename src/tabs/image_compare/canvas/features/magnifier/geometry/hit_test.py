from __future__ import annotations

from domain.types import Point
from ui.canvas_infra.scene.models import CanvasSceneGraph

from tabs.image_compare.canvas.features.magnifier.scene.objects import MagnifierCircle, MagnifierSceneObject


def _distance_squared(point: Point, circle: MagnifierCircle) -> float:
    dx = point.x - circle.center.x
    dy = point.y - circle.center.y
    return (dx * dx) + (dy * dy)


def circle_contains(circle: MagnifierCircle, point: Point) -> bool:
    if not circle.visible or circle.radius <= 0:
        return False
    return _distance_squared(point, circle) <= (circle.radius * circle.radius)


def _capture_contains(obj: MagnifierSceneObject, point: Point) -> bool:
    if obj.capture_center is None or obj.capture_radius <= 0:
        return False
    capture_circle = MagnifierCircle(
        center=obj.capture_center,
        radius=obj.capture_radius,
        role="capture",
        visible=True,
    )
    return circle_contains(capture_circle, point)


def find_magnifier_at_position(
    scene: CanvasSceneGraph,
    point: Point,
) -> MagnifierSceneObject | None:
    candidates = [
        obj
        for obj in scene.iter_pick_objects(kind="magnifier")
        if isinstance(obj, MagnifierSceneObject)
    ]
    best_match = None
    best_distance = None
    for obj in candidates:
        if _capture_contains(obj, point):
            distance = _distance_squared(
                point,
                MagnifierCircle(
                    center=obj.capture_center,
                    radius=obj.capture_radius,
                    role="capture",
                    visible=True,
                ),
            )
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_match = obj
        for circle in obj.circles:
            if not circle_contains(circle, point):
                continue
            distance = _distance_squared(point, circle)
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_match = obj
    return best_match


def get_active_magnifier(scene: CanvasSceneGraph) -> MagnifierSceneObject | None:
    active = scene.get_object(scene.active_object_id)
    if isinstance(active, MagnifierSceneObject) and active.visible:
        return active
    for obj in scene.iter_objects(kind="magnifier"):
        if isinstance(obj, MagnifierSceneObject) and obj.visible:
            return obj
    return None
