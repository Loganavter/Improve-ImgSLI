from dataclasses import dataclass

from core.state_management.action_base import Action, ActionType

@dataclass
class SetInteractiveModeAction(Action):
    enabled: bool

    def __init__(self, enabled: bool):
        super().__init__(type=ActionType.SET_INTERACTIVE_MODE)
        self.enabled = enabled

    def get_payload(self):
        return {"enabled": self.enabled}

@dataclass
class SetDraggingSplitLineAction(Action):
    enabled: bool

    def __init__(self, enabled: bool):
        super().__init__(type=ActionType.SET_IS_DRAGGING_SPLIT_LINE)
        self.enabled = enabled

    def get_payload(self):
        return {"enabled": self.enabled}

@dataclass
class SetDraggingCapturePointAction(Action):
    enabled: bool

    def __init__(self, enabled: bool):
        super().__init__(type=ActionType.SET_IS_DRAGGING_CAPTURE_POINT)
        self.enabled = enabled

    def get_payload(self):
        return {"enabled": self.enabled}

@dataclass
class SetDraggingSplitInMagnifierAction(Action):
    enabled: bool

    def __init__(self, enabled: bool):
        super().__init__(type=ActionType.SET_IS_DRAGGING_SPLIT_IN_MAGNIFIER)
        self.enabled = enabled

    def get_payload(self):
        return {"enabled": self.enabled}

@dataclass
class SetResizeInProgressAction(Action):
    enabled: bool

    def __init__(self, enabled: bool):
        super().__init__(type=ActionType.SET_RESIZE_IN_PROGRESS)
        self.enabled = enabled

    def get_payload(self):
        return {"enabled": self.enabled}

@dataclass
class SetPressedKeysAction(Action):
    keys: set[int]

    def __init__(self, keys: set[int]):
        super().__init__(type=ActionType.SET_PRESSED_KEYS)
        self.keys = set(keys)

    def get_payload(self):
        return {"keys": self.keys}

@dataclass
class SetSpaceBarPressedAction(Action):
    enabled: bool

    def __init__(self, enabled: bool):
        super().__init__(type=ActionType.SET_SPACE_BAR_PRESSED)
        self.enabled = enabled

    def get_payload(self):
        return {"enabled": self.enabled}

@dataclass
class SetInteractionSessionIdAction(Action):
    session_id: int

    def __init__(self, session_id: int):
        super().__init__(type=ActionType.SET_INTERACTION_SESSION_ID)
        self.session_id = session_id

    def get_payload(self):
        return {"session_id": self.session_id}

@dataclass
class SetUserInteractingAction(Action):
    enabled: bool

    def __init__(self, enabled: bool):
        super().__init__(type=ActionType.SET_USER_INTERACTING)
        self.enabled = enabled

    def get_payload(self):
        return {"enabled": self.enabled}

@dataclass
class SetLastHorizontalMovementKeyAction(Action):
    key: int | None

    def __init__(self, key: int | None):
        super().__init__(type=ActionType.SET_LAST_HORIZONTAL_MOVEMENT_KEY)
        self.key = key

    def get_payload(self):
        return {"key": self.key}

@dataclass
class SetLastVerticalMovementKeyAction(Action):
    key: int | None

    def __init__(self, key: int | None):
        super().__init__(type=ActionType.SET_LAST_VERTICAL_MOVEMENT_KEY)
        self.key = key

    def get_payload(self):
        return {"key": self.key}

@dataclass
class SetLastSpacingMovementKeyAction(Action):
    key: int | None

    def __init__(self, key: int | None):
        super().__init__(type=ActionType.SET_LAST_SPACING_MOVEMENT_KEY)
        self.key = key

    def get_payload(self):
        return {"key": self.key}
