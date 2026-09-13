from __future__ import annotations

from dataclasses import dataclass, field

from core.state_management.action_base import Action
from domain.types import Color


@dataclass
class SetDividerVisibleAction(Action):
    visible: bool
    type: str = field(default="SET_DIVIDER_VISIBLE", kw_only=True)

    def get_payload(self):
        return {"visible": self.visible}


@dataclass
class SetDividerColorAction(Action):
    color: Color
    type: str = field(default="SET_DIVIDER_COLOR", kw_only=True)

    def get_payload(self):
        return {"color": self.color}


@dataclass
class SetDividerThicknessAction(Action):
    thickness: int
    type: str = field(default="SET_DIVIDER_THICKNESS", kw_only=True)

    def get_payload(self):
        return {"thickness": self.thickness}
