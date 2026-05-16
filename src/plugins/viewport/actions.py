"""Magnifier-specific action classes owned by the viewport plugin."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from domain.types import Point

from core.state_management.action_base import Action

@dataclass
class SetMagnifierSizeRelativeAction(Action):
    size: float
    def __init__(self, size: float):
        super().__init__(type="SET_MAGNIFIER_SIZE_RELATIVE"); self.size = size
    def get_payload(self): return {"size": self.size}

@dataclass
class SetCaptureSizeRelativeAction(Action):
    size: float
    def __init__(self, size: float):
        super().__init__(type="SET_CAPTURE_SIZE_RELATIVE"); self.size = size
    def get_payload(self): return {"size": self.size}

@dataclass
class ToggleMagnifierAction(Action):
    enabled: bool
    def __init__(self, enabled: bool):
        super().__init__(type="TOGGLE_MAGNIFIER"); self.enabled = enabled
    def get_payload(self): return {"enabled": self.enabled}

@dataclass
class SetMagnifierVisibilityAction(Action):
    left: Optional[bool] = None
    center: Optional[bool] = None
    right: Optional[bool] = None
    def __init__(self, left: Optional[bool] = None, center: Optional[bool] = None, right: Optional[bool] = None):
        super().__init__(type="SET_MAGNIFIER_VISIBILITY"); self.left = left; self.center = center; self.right = right
    def get_payload(self): return {"left": self.left, "center": self.center, "right": self.right}

@dataclass
class ToggleMagnifierOrientationAction(Action):
    is_horizontal: bool
    def __init__(self, is_horizontal: bool):
        super().__init__(type="TOGGLE_MAGNIFIER_ORIENTATION"); self.is_horizontal = is_horizontal
    def get_payload(self): return {"is_horizontal": self.is_horizontal}

@dataclass
class ToggleFreezeMagnifierAction(Action):
    freeze: bool
    frozen_position: Optional[Point] = None
    new_offset: Optional[Point] = None
    def __init__(self, freeze: bool, frozen_position: Optional[Point] = None, new_offset: Optional[Point] = None):
        super().__init__(type="TOGGLE_FREEZE_MAGNIFIER"); self.freeze = freeze; self.frozen_position = frozen_position; self.new_offset = new_offset
    def get_payload(self): return {"freeze": self.freeze, "frozen_position": self.frozen_position, "new_offset": self.new_offset}

@dataclass
class SetMagnifierPositionAction(Action):
    position: Point
    def __init__(self, position: Point):
        super().__init__(type="SET_MAGNIFIER_POSITION"); self.position = position
    def get_payload(self): return {"position": self.position}

@dataclass
class SetMagnifierInternalSplitAction(Action):
    split: float
    def __init__(self, split: float):
        super().__init__(type="SET_MAGNIFIER_INTERNAL_SPLIT"); self.split = split
    def get_payload(self): return {"split": self.split}

@dataclass
class UpdateMagnifierCombinedStateAction(Action):
    is_combined: bool
    def __init__(self, is_combined: bool):
        super().__init__(type="UPDATE_MAGNIFIER_COMBINED_STATE"); self.is_combined = is_combined
    def get_payload(self): return {"is_combined": self.is_combined}

@dataclass
class SetActiveMagnifierIdAction(Action):
    magnifier_id: str
    def __init__(self, magnifier_id: str):
        super().__init__(type="SET_ACTIVE_MAGNIFIER_ID"); self.magnifier_id = magnifier_id
    def get_payload(self): return {"magnifier_id": self.magnifier_id}

@dataclass
class SetMagnifierOffsetRelativeAction(Action):
    offset: Point
    def __init__(self, offset: Point):
        super().__init__(type="SET_MAGNIFIER_OFFSET_RELATIVE"); self.offset = offset
    def get_payload(self): return {"offset": self.offset}

@dataclass
class SetMagnifierSpacingRelativeAction(Action):
    spacing: float
    def __init__(self, spacing: float):
        super().__init__(type="SET_MAGNIFIER_SPACING_RELATIVE"); self.spacing = spacing
    def get_payload(self): return {"spacing": self.spacing}

@dataclass
class SetMagnifierOffsetRelativeVisualAction(Action):
    offset: Point
    def __init__(self, offset: Point):
        super().__init__(type="SET_MAGNIFIER_OFFSET_RELATIVE_VISUAL"); self.offset = offset
    def get_payload(self): return {"offset": self.offset}

@dataclass
class SetMagnifierSpacingRelativeVisualAction(Action):
    spacing: float
    def __init__(self, spacing: float):
        super().__init__(type="SET_MAGNIFIER_SPACING_RELATIVE_VISUAL"); self.spacing = spacing
    def get_payload(self): return {"spacing": self.spacing}

@dataclass
class SetOptimizeMagnifierMovementAction(Action):
    enabled: bool
    def __init__(self, enabled: bool):
        super().__init__(type="SET_OPTIMIZE_MAGNIFIER_MOVEMENT"); self.enabled = enabled
    def get_payload(self): return {"enabled": self.enabled}

@dataclass
class SetHighlightedMagnifierElementAction(Action):
    element: Optional[str]
    def __init__(self, element: Optional[str]):
        super().__init__(type="SET_HIGHLIGHTED_MAGNIFIER_ELEMENT"); self.element = element
    def get_payload(self): return {"element": self.element}

@dataclass
class SetMagnifierLaserEnabledAction(Action):
    enabled: bool
    def __init__(self, enabled: bool):
        super().__init__(type="SET_MAGNIFIER_LASER_ENABLED"); self.enabled = enabled
    def get_payload(self): return {"enabled": self.enabled}

@dataclass
class SetMagnifierMovementInterpolationMethodAction(Action):
    method: str
    def __init__(self, method: str):
        super().__init__(type="SET_MAGNIFIER_MOVEMENT_INTERPOLATION_METHOD"); self.method = method
    def get_payload(self): return {"method": self.method}

@dataclass
class SetMagnifierScreenCenterAction(Action):
    center: Point
    def __init__(self, center: Point):
        super().__init__(type="SET_MAGNIFIER_SCREEN_CENTER"); self.center = center
    def get_payload(self): return {"center": self.center}

@dataclass
class SetMagnifierScreenSizeAction(Action):
    size: int
    def __init__(self, size: int):
        super().__init__(type="SET_MAGNIFIER_SCREEN_SIZE"); self.size = size
    def get_payload(self): return {"size": self.size}

@dataclass
class SetDraggingCapturePointAction(Action):
    enabled: bool
    def __init__(self, enabled: bool):
        super().__init__(type="SET_IS_DRAGGING_CAPTURE_POINT"); self.enabled = enabled
    def get_payload(self): return {"enabled": self.enabled}

@dataclass
class SetDraggingSplitInMagnifierAction(Action):
    enabled: bool
    def __init__(self, enabled: bool):
        super().__init__(type="SET_IS_DRAGGING_SPLIT_IN_MAGNIFIER"); self.enabled = enabled
    def get_payload(self): return {"enabled": self.enabled}

@dataclass
class SetInteractiveOffsetVisualAction(Action):
    offset: Point
    def __init__(self, offset: Point):
        super().__init__(type="SET_INTERACTIVE_OFFSET_VISUAL"); self.offset = offset
    def get_payload(self): return {"offset": self.offset}

@dataclass
class SetInteractiveSpacingVisualAction(Action):
    spacing: float
    def __init__(self, spacing: float):
        super().__init__(type="SET_INTERACTIVE_SPACING_VISUAL"); self.spacing = spacing
    def get_payload(self): return {"spacing": self.spacing}

@dataclass
class SetInteractiveInternalSplitVisualAction(Action):
    split: float
    def __init__(self, split: float):
        super().__init__(type="SET_INTERACTIVE_INTERNAL_SPLIT_VISUAL"); self.split = split
    def get_payload(self): return {"split": self.split}
