from dataclasses import dataclass

from core.state_management.action_base import Action, ActionType

@dataclass
class SetSplitPositionAction(Action):
    position: float
    def __init__(self, position: float):
        super().__init__(type=ActionType.SET_SPLIT_POSITION); self.position = position
    def get_payload(self): return {"position": self.position}

@dataclass
class SetSplitPositionVisualAction(Action):
    position: float
    def __init__(self, position: float):
        super().__init__(type=ActionType.SET_SPLIT_POSITION_VISUAL); self.position = position
    def get_payload(self): return {"position": self.position}

@dataclass
class ToggleOrientationAction(Action):
    is_horizontal: bool
    def __init__(self, is_horizontal: bool):
        super().__init__(type=ActionType.TOGGLE_ORIENTATION); self.is_horizontal = is_horizontal
    def get_payload(self): return {"is_horizontal": self.is_horizontal}

@dataclass
class SetMovementSpeedAction(Action):
    speed: float
    def __init__(self, speed: float):
        super().__init__(type=ActionType.SET_MOVEMENT_SPEED); self.speed = speed
    def get_payload(self): return {"speed": self.speed}

@dataclass
class SetIsDraggingSliderAction(Action):
    is_dragging: bool
    def __init__(self, is_dragging: bool):
        super().__init__(type=ActionType.SET_IS_DRAGGING_SLIDER); self.is_dragging = is_dragging
    def get_payload(self): return {"is_dragging": self.is_dragging}

@dataclass
class SetShowingSingleImageModeAction(Action):
    mode: int
    def __init__(self, mode: int):
        super().__init__(type=ActionType.SET_SHOWING_SINGLE_IMAGE_MODE); self.mode = mode
    def get_payload(self): return {"mode": self.mode}

@dataclass
class SetDiffModeAction(Action):
    mode: str
    def __init__(self, mode: str):
        super().__init__(type=ActionType.SET_DIFF_MODE); self.mode = mode
    def get_payload(self): return {"mode": self.mode}

@dataclass
class SetChannelViewModeAction(Action):
    mode: str
    def __init__(self, mode: str):
        super().__init__(type=ActionType.SET_CHANNEL_VIEW_MODE); self.mode = mode
    def get_payload(self): return {"mode": self.mode}

