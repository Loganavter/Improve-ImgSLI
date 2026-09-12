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
class SetPreviewImageAction(Action):
    slot: int
    image: Any
    def __init__(self, slot: int, image: Any):
        super().__init__(type=ActionType.SET_PREVIEW_IMAGE); self.slot = slot; self.image = image
    def get_payload(self): return {"slot": self.slot, "image": self.image}

@dataclass
class SetImagePathAction(Action):
    slot: int
    path: str
    def __init__(self, slot: int, path: str):
        super().__init__(type=ActionType.SET_IMAGE_PATH); self.slot = slot; self.path = path
    def get_payload(self): return {"slot": self.slot, "path": self.path}

@dataclass
class SetImageListAction(Action):
    slot: int
    items: list
    def __init__(self, slot: int, items: list):
        super().__init__(type=ActionType.SET_IMAGE_LIST); self.slot = slot; self.items = list(items)
    def get_payload(self): return {"slot": self.slot, "items": len(self.items)}

@dataclass
class AppendImageItemsAction(Action):
    slot: int
    items: list
    def __init__(self, slot: int, items: list):
        super().__init__(type=ActionType.APPEND_IMAGE_ITEMS); self.slot = slot; self.items = list(items)
    def get_payload(self): return {"slot": self.slot, "items": len(self.items)}

@dataclass
class SetCropOverrideAction(Action):
    """Per-image autocrop tristate override (W5).

    ``value`` is None (Auto — follow the global setting), True (force crop
    on) or False (force crop off). Handled by the owning tab's
    ``DocumentReducer`` (``state/reducer.py``) via ``dataclasses.replace``
    on the single ``ImageItem`` — never in-place. Wiring the value into the
    effective-box helper is a later wave; this action only stores it.
    """
    slot: int
    index: int
    value: bool | None
    def __init__(self, slot: int, index: int, value: bool | None):
        super().__init__(type=ActionType.SET_CROP_OVERRIDE); self.slot = slot; self.index = index; self.value = None if value is None else bool(value)
    def get_payload(self): return {"slot": self.slot, "index": self.index, "value": self.value}