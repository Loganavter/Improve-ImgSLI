from dataclasses import dataclass, field
from typing import Optional

from domain.types import Rect

from core.state_management.action_base import Action, ActionType

@dataclass
class SetPixmapDimensionsAction(Action):
    width: int
    height: int
    type: str = field(default=ActionType.SET_PIXMAP_DIMENSIONS.value, kw_only=True)

    def get_payload(self):
        return {"width": self.width, "height": self.height}

@dataclass
class SetImageDisplayRectAction(Action):
    rect: Rect
    type: str = field(default=ActionType.SET_IMAGE_DISPLAY_RECT.value, kw_only=True)

    def get_payload(self):
        return {"rect": self.rect}

@dataclass
class SetFixedLabelDimensionsAction(Action):
    width: Optional[int]
    height: Optional[int]
    type: str = field(default=ActionType.SET_FIXED_LABEL_DIMENSIONS.value, kw_only=True)

    def get_payload(self):
        return {"width": self.width, "height": self.height}
