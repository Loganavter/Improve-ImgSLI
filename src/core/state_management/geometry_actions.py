from dataclasses import dataclass
from typing import Optional

from domain.types import Point, Rect

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

@dataclass
class SetMagnifierScreenCenterAction(Action):
    center: Point

    def __init__(self, center: Point):
        super().__init__(type=ActionType.SET_MAGNIFIER_SCREEN_CENTER)
        self.center = center

    def get_payload(self):
        return {"center": self.center}

@dataclass
class SetMagnifierScreenSizeAction(Action):
    size: int

    def __init__(self, size: int):
        super().__init__(type=ActionType.SET_MAGNIFIER_SCREEN_SIZE)
        self.size = size

    def get_payload(self):
        return {"size": self.size}
