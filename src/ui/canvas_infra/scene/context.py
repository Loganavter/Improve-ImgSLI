from __future__ import annotations

from dataclasses import dataclass

from domain.types import Rect
from .pass_contract import SceneVisibility

@dataclass(frozen=True)
class CanvasSceneBuildContext:
    store: object
    image_label: object | None
    bounds: Rect
    label_width: int
    label_height: int
    pix_w: int
    pix_h: int

@dataclass(frozen=True)
class CanvasSceneApplyContext:
    canvas: object
    geometry_state: object
    use_quick_overlay: bool
    scene_visibility: SceneVisibility = SceneVisibility.INTERACTIVE
