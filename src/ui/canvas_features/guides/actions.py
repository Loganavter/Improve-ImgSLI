from __future__ import annotations

from dataclasses import dataclass

from core.state_management.action_base import Action
from domain.types import Color

@dataclass
class SetGuidesEnabledAction(Action):
    enabled: bool

    def __init__(self, enabled: bool):
        super().__init__(type="SET_GUIDES_ENABLED")
        self.enabled = bool(enabled)

    def get_payload(self):
        return {"enabled": self.enabled}

@dataclass
class SetGuidesThicknessAction(Action):
    thickness: int

    def __init__(self, thickness: int):
        super().__init__(type="SET_GUIDES_THICKNESS")
        self.thickness = int(thickness)

    def get_payload(self):
        return {"thickness": self.thickness}

@dataclass
class SetGuidesColorAction(Action):
    color: Color

    def __init__(self, color: Color):
        super().__init__(type="SET_GUIDES_COLOR")
        self.color = color

    def get_payload(self):
        return {"color": self.color}

@dataclass
class SetGuidesSmoothingEnabledAction(Action):
    enabled: bool

    def __init__(self, enabled: bool):
        super().__init__(type="SET_GUIDES_SMOOTHING_ENABLED")
        self.enabled = bool(enabled)

    def get_payload(self):
        return {"enabled": self.enabled}

@dataclass
class SetGuidesSmoothingInterpolationMethodAction(Action):
    method: str

    def __init__(self, method: str):
        super().__init__(type="SET_GUIDES_SMOOTHING_INTERPOLATION_METHOD")
        self.method = str(method)

    def get_payload(self):
        return {"method": self.method}
