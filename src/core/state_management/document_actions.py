from dataclasses import dataclass
from typing import Any

from core.state_management.action_base import Action, ActionType

@dataclass
class SetCurrentIndexAction(Action):
    slot: int
    index: int
    def __init__(self, slot: int, index: int):
        super().__init__(type=ActionType.SET_CURRENT_INDEX); self.slot = slot; self.index = index
    def get_payload(self): return {"slot": self.slot, "index": self.index}

@dataclass
class SetOriginalImageAction(Action):
    slot: int
    image: Any
    def __init__(self, slot: int, image: Any):
        super().__init__(type=ActionType.SET_ORIGINAL_IMAGE); self.slot = slot; self.image = image
    def get_payload(self): return {"slot": self.slot, "image": self.image}

@dataclass
class SetFullResImageAction(Action):
    slot: int
    image: Any
    def __init__(self, slot: int, image: Any):
        super().__init__(type=ActionType.SET_FULL_RES_IMAGE); self.slot = slot; self.image = image
    def get_payload(self): return {"slot": self.slot, "image": self.image}

@dataclass
class SetImagePathAction(Action):
    slot: int
    path: str
    def __init__(self, slot: int, path: str):
        super().__init__(type=ActionType.SET_IMAGE_PATH); self.slot = slot; self.path = path
    def get_payload(self): return {"slot": self.slot, "path": self.path}
