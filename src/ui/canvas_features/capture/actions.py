from __future__ import annotations

from dataclasses import dataclass

from core.state_management.action_base import Action, ActionType
from domain.types import Color

@dataclass
class SetCaptureVisibleAction(Action):
    enabled: bool

    def __init__(self, enabled: bool):
        super().__init__(type=ActionType.SET_CAPTURE_VISIBLE)
        self.enabled = bool(enabled)

    def get_payload(self):
        return {"enabled": self.enabled}

@dataclass
class SetCaptureColorAction(Action):
    color: Color

    def __init__(self, color: Color):
        super().__init__(type=ActionType.SET_CAPTURE_COLOR)
        self.color = color

    def get_payload(self):
        return {"color": self.color}
