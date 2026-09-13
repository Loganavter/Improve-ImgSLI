from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.state_management.action_base import Action, ActionType

if TYPE_CHECKING:
    from domain.types import Point

@dataclass
class SetInteractiveModeAction(Action):
    enabled: bool
    type: str = field(default=ActionType.SET_INTERACTIVE_MODE.value, kw_only=True)

    def get_payload(self):
        return {"enabled": self.enabled}

@dataclass
class SetDraggingSplitLineAction(Action):
    enabled: bool
    type: str = field(default=ActionType.SET_IS_DRAGGING_SPLIT_LINE.value, kw_only=True)

    def get_payload(self):
        return {"enabled": self.enabled}

@dataclass
class SetResizeInProgressAction(Action):
    enabled: bool
    type: str = field(default=ActionType.SET_RESIZE_IN_PROGRESS.value, kw_only=True)

    def get_payload(self):
        return {"enabled": self.enabled}

@dataclass
class SetPressedKeysAction(Action):
    keys: set[int]
    type: str = field(default=ActionType.SET_PRESSED_KEYS.value, kw_only=True)

    def __post_init__(self):
        self.keys = set(self.keys)

    def get_payload(self):
        return {"keys": self.keys}

@dataclass
class SetSpaceBarPressedAction(Action):
    enabled: bool
    type: str = field(default=ActionType.SET_SPACE_BAR_PRESSED.value, kw_only=True)

    def get_payload(self):
        return {"enabled": self.enabled}

@dataclass
class SetInteractionSessionIdAction(Action):
    session_id: int
    type: str = field(default=ActionType.SET_INTERACTION_SESSION_ID.value, kw_only=True)

    def get_payload(self):
        return {"session_id": self.session_id}

@dataclass
class SetUserInteractingAction(Action):
    enabled: bool
    type: str = field(default=ActionType.SET_USER_INTERACTING.value, kw_only=True)

    def get_payload(self):
        return {"enabled": self.enabled}

@dataclass
class SetLastHorizontalMovementKeyAction(Action):
    key: int | None
    type: str = field(default=ActionType.SET_LAST_HORIZONTAL_MOVEMENT_KEY.value, kw_only=True)

    def get_payload(self):
        return {"key": self.key}

@dataclass
class SetLastVerticalMovementKeyAction(Action):
    key: int | None
    type: str = field(default=ActionType.SET_LAST_VERTICAL_MOVEMENT_KEY.value, kw_only=True)

    def get_payload(self):
        return {"key": self.key}

@dataclass
class SetLastSpacingMovementKeyAction(Action):
    key: int | None
    type: str = field(default=ActionType.SET_LAST_SPACING_MOVEMENT_KEY.value, kw_only=True)

    def get_payload(self):
        return {"key": self.key}

@dataclass
class SetInteractiveOffsetVisualAction(Action):
    """Generic interactive visual state mutation (feature-agnostic)."""
    offset: "Point"
    type: str = field(default=ActionType.SET_INTERACTIVE_OFFSET_VISUAL.value, kw_only=True)

    def __post_init__(self):
        from domain.types import Point
        offset = self.offset
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
    type: str = field(default=ActionType.SET_INTERACTIVE_SPACING_VISUAL.value, kw_only=True)

    def get_payload(self):
        return {"spacing": self.spacing}

@dataclass
class SetInteractiveInternalSplitVisualAction(Action):
    """Generic interactive split visual state mutation (feature-agnostic)."""
    split: float
    type: str = field(default=ActionType.SET_INTERACTIVE_INTERNAL_SPLIT_VISUAL.value, kw_only=True)

    def get_payload(self):
        return {"split": self.split}
