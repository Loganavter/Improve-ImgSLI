from dataclasses import dataclass, field

from core.state_management.action_base import Action, ActionType

@dataclass
class SetSplitPositionAction(Action):
    position: float
    type: str = field(default=ActionType.SET_SPLIT_POSITION.value, kw_only=True)
    def get_payload(self): return {"position": self.position}

@dataclass
class SetSplitPositionVisualAction(Action):
    position: float
    type: str = field(default=ActionType.SET_SPLIT_POSITION_VISUAL.value, kw_only=True)
    def get_payload(self): return {"position": self.position}

@dataclass
class ToggleOrientationAction(Action):
    is_horizontal: bool
    type: str = field(default=ActionType.TOGGLE_ORIENTATION.value, kw_only=True)
    def get_payload(self): return {"is_horizontal": self.is_horizontal}

@dataclass
class SetMovementSpeedAction(Action):
    speed: float
    type: str = field(default=ActionType.SET_MOVEMENT_SPEED.value, kw_only=True)
    def get_payload(self): return {"speed": self.speed}

@dataclass
class SetIsDraggingSliderAction(Action):
    is_dragging: bool
    type: str = field(default=ActionType.SET_IS_DRAGGING_SLIDER.value, kw_only=True)
    def get_payload(self): return {"is_dragging": self.is_dragging}

@dataclass
class SetShowingSingleImageModeAction(Action):
    mode: int
    type: str = field(default=ActionType.SET_SHOWING_SINGLE_IMAGE_MODE.value, kw_only=True)
    def get_payload(self): return {"mode": self.mode}

@dataclass
class SetDiffModeAction(Action):
    mode: str
    type: str = field(default=ActionType.SET_DIFF_MODE.value, kw_only=True)
    def get_payload(self): return {"mode": self.mode}

@dataclass
class SetChannelViewModeAction(Action):
    mode: str
    type: str = field(default=ActionType.SET_CHANNEL_VIEW_MODE.value, kw_only=True)
    def get_payload(self): return {"mode": self.mode}

@dataclass
class SetCanvasWidgetStateAction(Action):
    """Redux action for `view_state.canvas_widget_state[feature] = state`."""

    feature: str
    state: object
    type: str = field(default=ActionType.SET_CANVAS_WIDGET_STATE.value, kw_only=True)

    def __post_init__(self):
        self.feature = str(self.feature)

    def get_payload(self):
        return {"feature": self.feature, "state": self.state}
