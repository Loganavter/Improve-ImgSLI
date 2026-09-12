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

@dataclass
class SetInteractiveOffsetVisualAction(Action):
    """Generic interactive visual state mutation (feature-agnostic)."""
    offset: "Point"

    def __init__(self, offset):
        from domain.types import Point
        super().__init__(type=ActionType.SET_INTERACTIVE_OFFSET_VISUAL)

        if isinstance(offset, Point):
            self.offset = offset
        elif hasattr(offset, 'x'):
            self.offset = Point(offset.x, offset.y)
        else:
            self.offset = Point(float(offset[0]), float(offset[1]))

    def get_payload(self):
        return {"offset": (self.offset.x, self.offset.y)}

@dataclass
class SetInteractiveSpacingVisualAction(Action):
    """Generic interactive spacing visual state mutation (feature-agnostic)."""
    spacing: float

    def __init__(self, spacing: float):
        super().__init__(type=ActionType.SET_INTERACTIVE_SPACING_VISUAL)
        self.spacing = spacing

    def get_payload(self):
        return {"spacing": self.spacing}

@dataclass
class SetInteractiveInternalSplitVisualAction(Action):
    """Generic interactive split visual state mutation (feature-agnostic)."""
    split: float

    def __init__(self, split: float):
        super().__init__(type=ActionType.SET_INTERACTIVE_INTERNAL_SPLIT_VISUAL)
        self.split = split

    def get_payload(self):
        return {"split": self.split}
