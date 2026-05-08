from __future__ import annotations

from dataclasses import dataclass, field

from domain.types import Color, Point
from ui.canvas_infra.scene.models import CanvasSceneObject

@dataclass(frozen=True)
class GuidesSceneObject(CanvasSceneObject):
    source_center: Point | None = None
    target_centers: tuple[Point, ...] = ()
    source_radius: float = 0.0
    target_radius: float = 0.0
    target_radii: tuple[float, ...] = ()
    color: Color = field(default_factory=Color)
    thickness: int = 1
