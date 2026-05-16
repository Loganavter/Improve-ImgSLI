from __future__ import annotations

from dataclasses import dataclass

@dataclass
class SunburstSegmentData:
    """Data for a single sunburst chart segment.

    Angles are in radians. Radii are normalized (0.0–1.0).
    """

    start_angle: float
    end_angle: float
    inner_radius: float
    outer_radius: float
    color: str
    label: str = ""
    font_size: int = 0
    node_id: str = ""
    value_text: str = ""
    tooltip: str = ""
    is_clickable: bool = True
    is_disabled: bool = False
