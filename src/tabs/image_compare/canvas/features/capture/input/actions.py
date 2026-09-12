from __future__ import annotations

from dataclasses import dataclass, field

from core.state_management.action_base import Action
from domain.types import Color


@dataclass
class SetCaptureSizeRelativeAction(Action):
    size: float
    type: str = field(default="SET_CAPTURE_SIZE_RELATIVE", kw_only=True)

    def __post_init__(self):
        self.size = float(self.size)

    def get_payload(self):
        return {"size": self.size}


@dataclass
class SetCaptureVisibleAction(Action):
    enabled: bool
    type: str = field(default="SET_CAPTURE_VISIBLE", kw_only=True)

    def __post_init__(self):
        self.enabled = bool(self.enabled)

    def get_payload(self):
        return {"enabled": self.enabled}


@dataclass
class SetCaptureColorAction(Action):
    color: Color
    type: str = field(default="SET_CAPTURE_COLOR", kw_only=True)

    def get_payload(self):
        return {"color": self.color}
