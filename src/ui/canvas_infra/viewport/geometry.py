from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class QuickContentRect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height


def resolve_axis_position(offset: float, size: float, fraction: float) -> float:
    """Where a normalized ``fraction`` along one axis of a rect sits in
    absolute units. The one primitive every split-position/divider screen
    mapping is built from — see
    docs/dev/CANVAS_CONTENT_GEOMETRY_REFACTOR.md."""
    return float(offset) + float(size) * float(fraction)
