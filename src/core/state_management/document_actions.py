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
    type: str = field(default=ActionType.SET_CROP_OVERRIDE.value, kw_only=True)
    def __post_init__(self): self.value = None if self.value is None else bool(self.value)
    def get_payload(self): return {"slot": self.slot, "index": self.index, "value": self.value}
