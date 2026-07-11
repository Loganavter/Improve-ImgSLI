from __future__ import annotations

from dataclasses import dataclass

from core.state_management.action_base import Action
from domain.types import Color


@dataclass
class SetDividerVisibleAction(Action):
    visible: bool

    def __init__(self, visible: bool):
        super().__init__(type="SET_DIVIDER_VISIBLE")
        self.visible = visible

    def get_payload(self):
        return {"visible": self.visible}


@dataclass
class SetDividerColorAction(Action):
    color: Color

    def __init__(self, color: Color):
        super().__init__(type="SET_DIVIDER_COLOR")
        self.color = color

    def get_payload(self):
        return {"color": self.color}


@dataclass
class SetDividerThicknessAction(Action):
    thickness: int

    def __init__(self, thickness: int):
        super().__init__(type="SET_DIVIDER_THICKNESS")
        self.thickness = thickness

    def get_payload(self):
        return {"thickness": self.thickness}
