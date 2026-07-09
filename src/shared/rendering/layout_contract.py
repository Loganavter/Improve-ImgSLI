from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

@dataclass(slots=True, frozen=True)
class NormalizedBounds:
    x_min: float
    x_max: float
    y_min: float
    y_max: float

    @staticmethod
    def unit() -> "NormalizedBounds":
        return NormalizedBounds(0.0, 1.0, 0.0, 1.0)

    @property
    def width(self) -> float:
        return float(self.x_max - self.x_min)

    @property
    def height(self) -> float:
        return float(self.y_max - self.y_min)

    def union(self, other: "NormalizedBounds") -> "NormalizedBounds":
        return NormalizedBounds(
            x_min=min(float(self.x_min), float(other.x_min)),
            x_max=max(float(self.x_max), float(other.x_max)),
            y_min=min(float(self.y_min), float(other.y_min)),
            y_max=max(float(self.y_max), float(other.y_max)),
        )

@dataclass(slots=True, frozen=True)
class FeatureLayoutRequirement:
    feature_id: str
    bounds: NormalizedBounds

@dataclass(slots=True, frozen=True)
class VirtualCanvasLayout:
    canvas_bounds: NormalizedBounds
    content_bounds: NormalizedBounds

    @property
    def pad_left_units(self) -> float:
        return float(self.content_bounds.x_min - self.canvas_bounds.x_min)

    @property
    def pad_right_units(self) -> float:
        return float(self.canvas_bounds.x_max - self.content_bounds.x_max)

    @property
    def pad_top_units(self) -> float:
        return float(self.content_bounds.y_min - self.canvas_bounds.y_min)

    @property
    def pad_bottom_units(self) -> float:
        return float(self.canvas_bounds.y_max - self.content_bounds.y_max)

    def resolve_padding_pixels(
        self,
        *,
        base_width: int,
        base_height: int,
    ) -> tuple[int, int, int, int]:
        width = max(1, int(base_width))
        height = max(1, int(base_height))
        pad_left = max(0, int(round(self.pad_left_units * width)))
        pad_right = max(0, int(round(self.pad_right_units * width)))
        pad_top = max(0, int(round(self.pad_top_units * height)))
        pad_bottom = max(0, int(round(self.pad_bottom_units * height)))
        return pad_left, pad_right, pad_top, pad_bottom

def resolve_virtual_canvas_layout(
    requirements: Iterable[FeatureLayoutRequirement],
    *,
    content_bounds: NormalizedBounds | None = None,
) -> VirtualCanvasLayout:
    base_bounds = content_bounds or NormalizedBounds.unit()
    canvas_bounds = base_bounds
    for requirement in requirements:
        canvas_bounds = canvas_bounds.union(requirement.bounds)
    return VirtualCanvasLayout(
        canvas_bounds=canvas_bounds,
        content_bounds=base_bounds,
    )

