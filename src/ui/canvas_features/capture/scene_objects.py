from __future__ import annotations

from dataclasses import dataclass, field

from domain.types import Color, Point
from ui.canvas_infra.scene.models import CanvasSceneObject

@dataclass(frozen=True)
class CaptureSceneObject(CanvasSceneObject):
    center: Point | None = None
    radius: float = 0.0
    color: Color = field(default_factory=Color)
