from dataclasses import dataclass, field
from typing import Any

from core.state_management.action_base import Action, ActionType

@dataclass
class SetCurrentIndexAction(Action):
    slot: int
    index: int
    type: str = field(default=ActionType.SET_CURRENT_INDEX.value, kw_only=True)
    def get_payload(self): return {"slot": self.slot, "index": self.index}

@dataclass
class SetOriginalImageAction(Action):
    slot: int
    image: Any
    type: str = field(default=ActionType.SET_ORIGINAL_IMAGE.value, kw_only=True)
    def get_payload(self): return {"slot": self.slot, "image": self.image}

@dataclass
class SetFullResImageAction(Action):
    slot: int
    image: Any
    type: str = field(default=ActionType.SET_FULL_RES_IMAGE.value, kw_only=True)
    def get_payload(self): return {"slot": self.slot, "image": self.image}

@dataclass
class SetPreviewImageAction(Action):
    slot: int
    image: Any
    type: str = field(default=ActionType.SET_PREVIEW_IMAGE.value, kw_only=True)
    def get_payload(self): return {"slot": self.slot, "image": self.image}

@dataclass
class SetImagePathAction(Action):
    slot: int
    path: str
    type: str = field(default=ActionType.SET_IMAGE_PATH.value, kw_only=True)
    def get_payload(self): return {"slot": self.slot, "path": self.path}

@dataclass
class SetImageListAction(Action):
    slot: int
    items: list
    type: str = field(default=ActionType.SET_IMAGE_LIST.value, kw_only=True)
    def __post_init__(self): self.items = list(self.items)
    def get_payload(self): return {"slot": self.slot, "items": len(self.items)}

@dataclass
class AppendImageItemsAction(Action):
    slot: int
    items: list
    type: str = field(default=ActionType.APPEND_IMAGE_ITEMS.value, kw_only=True)
    def __post_init__(self): self.items = list(self.items)
    def get_payload(self): return {"slot": self.slot, "items": len(self.items)}
