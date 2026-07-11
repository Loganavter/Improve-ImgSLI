from __future__ import annotations

from dataclasses import dataclass, field

from domain.types import Color, Point
from ui.canvas_infra.scene.models import CanvasSceneObject


@dataclass(frozen=True)
class MagnifierCircle:
    center: Point
    radius: float
    role: str
    visible: bool = True


@dataclass(frozen=True)
class MagnifierSceneObject(CanvasSceneObject):
    source_position: Point = field(default_factory=Point)
    source_radius: float = 0.0
    capture_center: Point | None = None
    capture_radius: float = 0.0
    circles: tuple[MagnifierCircle, ...] = ()
    interactive_circle_index: int | None = None
    internal_split: float = 0.5
    is_horizontal: bool = False
    is_combined: bool = False
    divider_visible: bool = True
    divider_thickness: int = 1
    border_thickness: int = 2
    divider_color: Color = field(default_factory=Color)
    border_color: Color = field(default_factory=Color)
    capture_color: Color | None = None
    guides_color: Color | None = None
    show_laser: bool = True

    def interactive_circle(self) -> MagnifierCircle | None:
        if self.interactive_circle_index is None:
            return None
        if 0 <= self.interactive_circle_index < len(self.circles):
            return self.circles[self.interactive_circle_index]
        return None
