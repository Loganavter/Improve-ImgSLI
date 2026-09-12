from dataclasses import dataclass
from typing import Any, Optional

from core.state_management.action_base import Action, ActionType

@dataclass
class SetImageSessionImageAction(Action):
    slot: int
    image: Any

    def __init__(self, slot: int, image: Any):
        super().__init__(type=ActionType.SET_IMAGE_SESSION_IMAGE)
        self.slot = slot
        self.image = image

    def get_payload(self):
        return {"slot": self.slot, "image": self.image}

@dataclass
class SetUnificationInProgressAction(Action):
    enabled: bool

    def __init__(self, enabled: bool):
        super().__init__(type=ActionType.SET_UNIFICATION_IN_PROGRESS)
        self.enabled = enabled

    def get_payload(self):
        return {"enabled": self.enabled}

@dataclass
class SetPendingUnificationPathsAction(Action):
    paths: Optional[tuple[str, str]]

    def __init__(self, paths: Optional[tuple[str, str]]):
        super().__init__(type=ActionType.SET_PENDING_UNIFICATION_PATHS)
        self.paths = paths

    def get_payload(self):
        return {"paths": self.paths}

@dataclass
class SetZoomInterpolationMethodAction(Action):
    method: str

    def __init__(self, method: str):
        super().__init__(type=ActionType.SET_ZOOM_INTERPOLATION_METHOD)
        self.method = method

    def get_payload(self):
        return {"method": self.method}

@dataclass
class SetAutoCalculatePsnrAction(Action):
    enabled: bool

    def __init__(self, enabled: bool):
        super().__init__(type=ActionType.SET_AUTO_CALCULATE_PSNR)
        self.enabled = enabled

    def get_payload(self):
        return {"enabled": self.enabled}

@dataclass
class SetAutoCalculateSsimAction(Action):
    enabled: bool

    def __init__(self, enabled: bool):
        super().__init__(type=ActionType.SET_AUTO_CALCULATE_SSIM)
        self.enabled = enabled

    def get_payload(self):
        return {"enabled": self.enabled}

@dataclass
class SetPsnrValueAction(Action):
    value: Optional[float]

    def __init__(self, value: Optional[float]):
        super().__init__(type=ActionType.SET_PSNR_VALUE)
        self.value = value

    def get_payload(self):
        return {"value": self.value}

@dataclass
class SetSsimValueAction(Action):
    value: Optional[float]

    def __init__(self, value: Optional[float]):
        super().__init__(type=ActionType.SET_SSIM_VALUE)
        self.value = value

    def get_payload(self):
        return {"value": self.value}