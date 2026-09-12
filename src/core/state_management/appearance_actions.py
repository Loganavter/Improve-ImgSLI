from dataclasses import dataclass, field
from typing import Any

from domain.types import Color

from core.state_management.action_base import Action, ActionType

@dataclass
class SetCachedDiffImageAction(Action):
    image: Any
    type: str = field(default=ActionType.SET_CACHED_DIFF_IMAGE.value, kw_only=True)
    def get_payload(self): return {"image": self.image}

@dataclass
class SetIncludeFileNamesInSavedAction(Action):
    enabled: bool
    type: str = field(default=ActionType.SET_INCLUDE_FILE_NAMES_IN_SAVED.value, kw_only=True)
    def get_payload(self): return {"enabled": self.enabled}

@dataclass
class SetFontSizePercentAction(Action):
    size: int
    type: str = field(default=ActionType.SET_FONT_SIZE_PERCENT.value, kw_only=True)
    def get_payload(self): return {"size": self.size}

@dataclass
class SetFontWeightAction(Action):
    weight: int
    type: str = field(default=ActionType.SET_FONT_WEIGHT.value, kw_only=True)
    def get_payload(self): return {"weight": self.weight}

@dataclass
class SetTextAlphaPercentAction(Action):
    alpha: int
    type: str = field(default=ActionType.SET_TEXT_ALPHA_PERCENT.value, kw_only=True)
    def get_payload(self): return {"alpha": self.alpha}

@dataclass
class SetFileNameColorAction(Action):
    color: Color
    type: str = field(default=ActionType.SET_FILE_NAME_COLOR.value, kw_only=True)
    def get_payload(self): return {"color": self.color}

@dataclass
class SetFileNameBgColorAction(Action):
    color: Color
    type: str = field(default=ActionType.SET_FILE_NAME_BG_COLOR.value, kw_only=True)
    def get_payload(self): return {"color": self.color}

@dataclass
class SetDrawTextBackgroundAction(Action):
    enabled: bool
    type: str = field(default=ActionType.SET_DRAW_TEXT_BACKGROUND.value, kw_only=True)
    def get_payload(self): return {"enabled": self.enabled}

@dataclass
class SetTextPlacementModeAction(Action):
    mode: str
    type: str = field(default=ActionType.SET_TEXT_PLACEMENT_MODE.value, kw_only=True)
    def get_payload(self): return {"mode": self.mode}

@dataclass
class SetInterpolationMethodAction(Action):
    method: str
    type: str = field(default=ActionType.SET_INTERPOLATION_METHOD.value, kw_only=True)
    def get_payload(self): return {"method": self.method}

@dataclass
class SetMovementInterpolationMethodAction(Action):
    method: str
    type: str = field(default=ActionType.SET_MOVEMENT_INTERPOLATION_METHOD.value, kw_only=True)
    def get_payload(self): return {"method": self.method}

@dataclass
class SetMaxNameLengthAction(Action):
    length: int
    type: str = field(default=ActionType.SET_MAX_NAME_LENGTH.value, kw_only=True)
    def get_payload(self): return {"length": self.length}
