from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import QRect

@dataclass(frozen=True)
class CanvasGeometry:
    img_w: int
    img_h: int
    padding_left: int
    padding_top: int
    canvas_w: int
    canvas_h: int
    magnifier_bbox_on_canvas: Optional[QRect] = None

