from __future__ import annotations

from dataclasses import dataclass, field

from core.state_management.action_base import Action
from domain.types import Color


@dataclass
class SetGuidesEnabledAction(Action):
    enabled: bool
    type: str = field(default="SET_GUIDES_ENABLED", kw_only=True)

    def __post_init__(self):
        self.enabled = bool(self.enabled)

    def get_payload(self):
        return {"enabled": self.enabled}


@dataclass
class SetGuidesThicknessAction(Action):
    thickness: int
    type: str = field(default="SET_GUIDES_THICKNESS", kw_only=True)

    def __post_init__(self):
        self.thickness = int(self.thickness)

    def get_payload(self):
        return {"thickness": self.thickness}


@dataclass
class SetGuidesColorAction(Action):
    color: Color
    type: str = field(default="SET_GUIDES_COLOR", kw_only=True)

    def get_payload(self):
        return {"color": self.color}


@dataclass
class SetGuidesSmoothingEnabledAction(Action):
    enabled: bool
    type: str = field(default="SET_GUIDES_SMOOTHING_ENABLED", kw_only=True)

    def __post_init__(self):
        self.enabled = bool(self.enabled)

    def get_payload(self):
        return {"enabled": self.enabled}


@dataclass
class SetGuidesSmoothingInterpolationMethodAction(Action):
    method: str
    type: str = field(default="SET_GUIDES_SMOOTHING_INTERPOLATION_METHOD", kw_only=True)

    def __post_init__(self):
        self.method = str(self.method)

    def get_payload(self):
        return {"method": self.method}
