"""Magnifier-specific action classes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.state_management.action_base import Action
from domain.types import Point


@dataclass
class SetMagnifierSizeRelativeAction(Action):
    size: float
    type: str = field(default="SET_MAGNIFIER_SIZE_RELATIVE", kw_only=True)

    def get_payload(self):
        return {"size": self.size}


@dataclass
class SetCaptureSizeRelativeAction(Action):
    size: float
    type: str = field(default="SET_CAPTURE_SIZE_RELATIVE", kw_only=True)

    def get_payload(self):
        return {"size": self.size}


@dataclass
class ToggleMagnifierAction(Action):
    enabled: bool
    type: str = field(default="TOGGLE_MAGNIFIER", kw_only=True)

    def get_payload(self):
        return {"enabled": self.enabled}


@dataclass
class SetMagnifierVisibilityAction(Action):
    left: Optional[bool] = None
    center: Optional[bool] = None
    right: Optional[bool] = None
    type: str = field(default="SET_MAGNIFIER_VISIBILITY", kw_only=True)

    def get_payload(self):
        return {"left": self.left, "center": self.center, "right": self.right}


@dataclass
class ToggleMagnifierOrientationAction(Action):
    is_horizontal: bool
    type: str = field(default="TOGGLE_MAGNIFIER_ORIENTATION", kw_only=True)

    def get_payload(self):
        return {"is_horizontal": self.is_horizontal}


@dataclass
class ToggleFreezeMagnifierAction(Action):
    freeze: bool
    frozen_position: Optional[Point] = None
    new_offset: Optional[Point] = None
    type: str = field(default="TOGGLE_FREEZE_MAGNIFIER", kw_only=True)

    def get_payload(self):
        return {
            "freeze": self.freeze,
            "frozen_position": self.frozen_position,
            "new_offset": self.new_offset,
        }


@dataclass
class SetMagnifierPositionAction(Action):
    position: Point
    type: str = field(default="SET_MAGNIFIER_POSITION", kw_only=True)

    def get_payload(self):
        return {"position": self.position}


@dataclass
class SetMagnifierInternalSplitAction(Action):
    split: float
    type: str = field(default="SET_MAGNIFIER_INTERNAL_SPLIT", kw_only=True)

    def get_payload(self):
        return {"split": self.split}


@dataclass
class UpdateMagnifierCombinedStateAction(Action):
    is_combined: bool
    type: str = field(default="UPDATE_MAGNIFIER_COMBINED_STATE", kw_only=True)

    def get_payload(self):
        return {"is_combined": self.is_combined}


@dataclass
class SetActiveMagnifierIdAction(Action):
    magnifier_id: str
    type: str = field(default="SET_ACTIVE_MAGNIFIER_ID", kw_only=True)

    def get_payload(self):
        return {"magnifier_id": self.magnifier_id}


@dataclass
class SetMagnifierOffsetRelativeAction(Action):
    offset: Point
    type: str = field(default="SET_MAGNIFIER_OFFSET_RELATIVE", kw_only=True)

    def get_payload(self):
        return {"offset": self.offset}


@dataclass
class SetMagnifierSpacingRelativeAction(Action):
    spacing: float
    type: str = field(default="SET_MAGNIFIER_SPACING_RELATIVE", kw_only=True)

    def get_payload(self):
        return {"spacing": self.spacing}


@dataclass
class SetMagnifierOffsetRelativeVisualAction(Action):
    offset: Point
    type: str = field(default="SET_MAGNIFIER_OFFSET_RELATIVE_VISUAL", kw_only=True)

    def get_payload(self):
        return {"offset": self.offset}


@dataclass
class SetMagnifierSpacingRelativeVisualAction(Action):
    spacing: float
    type: str = field(default="SET_MAGNIFIER_SPACING_RELATIVE_VISUAL", kw_only=True)

    def get_payload(self):
        return {"spacing": self.spacing}


@dataclass
class SetOptimizeMagnifierMovementAction(Action):
    enabled: bool
    type: str = field(default="SET_OPTIMIZE_MAGNIFIER_MOVEMENT", kw_only=True)

    def get_payload(self):
        return {"enabled": self.enabled}


@dataclass
class SetHighlightedMagnifierElementAction(Action):
    element: Optional[str]
    type: str = field(default="SET_HIGHLIGHTED_MAGNIFIER_ELEMENT", kw_only=True)

    def get_payload(self):
        return {"element": self.element}


@dataclass
class SetMagnifierLaserEnabledAction(Action):
    enabled: bool
    type: str = field(default="SET_MAGNIFIER_LASER_ENABLED", kw_only=True)

    def get_payload(self):
        return {"enabled": self.enabled}


@dataclass
class SetMagnifierMovementInterpolationMethodAction(Action):
    method: str
    type: str = field(default="SET_MAGNIFIER_MOVEMENT_INTERPOLATION_METHOD", kw_only=True)

    def get_payload(self):
        return {"method": self.method}


@dataclass
class SetMagnifierScreenCenterAction(Action):
    center: Point
    type: str = field(default="SET_MAGNIFIER_SCREEN_CENTER", kw_only=True)

    def get_payload(self):
        return {"center": self.center}


@dataclass
class SetMagnifierScreenSizeAction(Action):
    size: int
    type: str = field(default="SET_MAGNIFIER_SCREEN_SIZE", kw_only=True)

    def get_payload(self):
        return {"size": self.size}


@dataclass
class SetDraggingCapturePointAction(Action):
    enabled: bool
    type: str = field(default="SET_IS_DRAGGING_CAPTURE_POINT", kw_only=True)

    def get_payload(self):
        return {"enabled": self.enabled}


@dataclass
class SetDraggingSplitInMagnifierAction(Action):
    enabled: bool
    type: str = field(default="SET_IS_DRAGGING_SPLIT_IN_MAGNIFIER", kw_only=True)

    def get_payload(self):
        return {"enabled": self.enabled}
