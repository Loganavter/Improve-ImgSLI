from dataclasses import dataclass
from typing import Any

from domain.types import Color

from core.state_management.action_base import Action, ActionType

@dataclass
class SetCachedDiffImageAction(Action):
    image: Any
    def __init__(self, image: Any):
        super().__init__(type=ActionType.SET_CACHED_DIFF_IMAGE); self.image = image
    def get_payload(self): return {"image": self.image}

@dataclass
class SetIncludeFileNamesInSavedAction(Action):
    enabled: bool
    def __init__(self, enabled: bool):
        super().__init__(type=ActionType.SET_INCLUDE_FILE_NAMES_IN_SAVED); self.enabled = enabled
    def get_payload(self): return {"enabled": self.enabled}

@dataclass
class SetFontSizePercentAction(Action):
    size: int
    def __init__(self, size: int):
        super().__init__(type=ActionType.SET_FONT_SIZE_PERCENT); self.size = size
    def get_payload(self): return {"size": self.size}

@dataclass
class SetFontWeightAction(Action):
    weight: int
    def __init__(self, weight: int):
        super().__init__(type=ActionType.SET_FONT_WEIGHT); self.weight = weight
    def get_payload(self): return {"weight": self.weight}

@dataclass
class SetTextAlphaPercentAction(Action):
    alpha: int
    def __init__(self, alpha: int):
        super().__init__(type=ActionType.SET_TEXT_ALPHA_PERCENT); self.alpha = alpha
    def get_payload(self): return {"alpha": self.alpha}

@dataclass
class SetFileNameColorAction(Action):
    color: Color
    def __init__(self, color: Color):
        super().__init__(type=ActionType.SET_FILE_NAME_COLOR); self.color = color
    def get_payload(self): return {"color": self.color}

@dataclass
class SetFileNameBgColorAction(Action):
    color: Color
    def __init__(self, color: Color):
        super().__init__(type=ActionType.SET_FILE_NAME_BG_COLOR); self.color = color
    def get_payload(self): return {"color": self.color}

@dataclass
class SetDrawTextBackgroundAction(Action):
    enabled: bool
    def __init__(self, enabled: bool):
        super().__init__(type=ActionType.SET_DRAW_TEXT_BACKGROUND); self.enabled = enabled
    def get_payload(self): return {"enabled": self.enabled}

@dataclass
class SetTextPlacementModeAction(Action):
    mode: str
    def __init__(self, mode: str):
        super().__init__(type=ActionType.SET_TEXT_PLACEMENT_MODE); self.mode = mode
    def get_payload(self): return {"mode": self.mode}

@dataclass
class SetInterpolationMethodAction(Action):
    method: str
    def __init__(self, method: str):
        super().__init__(type=ActionType.SET_INTERPOLATION_METHOD); self.method = method
    def get_payload(self): return {"method": self.method}

@dataclass
class SetMovementInterpolationMethodAction(Action):
    method: str
    def __init__(self, method: str):
        super().__init__(type=ActionType.SET_MOVEMENT_INTERPOLATION_METHOD); self.method = method
    def get_payload(self): return {"method": self.method}

@dataclass
class SetMaxNameLengthAction(Action):
    length: int
    def __init__(self, length: int):
        super().__init__(type=ActionType.SET_MAX_NAME_LENGTH); self.length = length
    def get_payload(self): return {"length": self.length}
