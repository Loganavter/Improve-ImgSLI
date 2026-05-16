from dataclasses import dataclass
from typing import Optional

from domain.types import Rect

from core.state_management.action_base import Action, ActionType

@dataclass
class SetPixmapDimensionsAction(Action):
    width: int
    height: int

    def __init__(self, width: int, height: int):
        super().__init__(type=ActionType.SET_PIXMAP_DIMENSIONS)
        self.width = width
        self.height = height

    def get_payload(self):
        return {"width": self.width, "height": self.height}

@dataclass
class SetImageDisplayRectAction(Action):
    rect: Rect

    def __init__(self, rect: Rect):
        super().__init__(type=ActionType.SET_IMAGE_DISPLAY_RECT)
        self.rect = rect

    def get_payload(self):
        return {"rect": self.rect}

@dataclass
class SetFixedLabelDimensionsAction(Action):
    width: Optional[int]
    height: Optional[int]

    def __init__(self, width: Optional[int], height: Optional[int]):
        super().__init__(type=ActionType.SET_FIXED_LABEL_DIMENSIONS)
        self.width = width
        self.height = height

    def get_payload(self):
        return {"width": self.width, "height": self.height}

