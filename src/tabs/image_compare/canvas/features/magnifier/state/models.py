"""Magnifier domain model — owned by the magnifier canvas feature."""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from typing import Optional

from domain.types import Color, Point


@dataclass
class MagnifierModel:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    visible: bool = True
    position: Point = field(default_factory=lambda: Point(0.5, 0.5))
    size_relative: float = 0.2
    capture_size_relative: float = 0.1

    border_color: Color = field(default_factory=lambda: Color(255, 255, 255, 230))
    divider_color: Color = field(default_factory=lambda: Color(255, 255, 255, 230))
    capture_color: Color | None = None
    guides_color: Color | None = None

    offset_relative: Point = field(default_factory=lambda: Point(0.0, 0.0))
    spacing_relative: float = 0.05
    is_horizontal: bool = False
    internal_split: float = 0.5
    divider_visible: bool = True
    divider_thickness: int = 2
    border_thickness: int = 2
    visible_left: bool = True
    visible_center: bool = True
    visible_right: bool = True
    freeze: bool = False
    frozen_position: Optional[Point] = None
    show_capture_area: bool = True
    show_laser: bool = True
    interpolation_method: str = "BILINEAR"

    def clone(self):
        return copy.copy(self)
