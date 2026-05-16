from __future__ import annotations

from dataclasses import dataclass

from domain.types import Point

@dataclass(frozen=True)
class ViewportSetSplitPositionEvent:
    position: float

@dataclass(frozen=True)
class ViewportUpdateMagnifierSizeRelativeEvent:
    relative_size: float

@dataclass(frozen=True)
class ViewportUpdateCaptureSizeRelativeEvent:
    relative_size: float

@dataclass(frozen=True)
class ViewportUpdateMovementSpeedEvent:
    speed: float

@dataclass(frozen=True)
class ViewportSetMagnifierPositionEvent:
    position: Point

@dataclass(frozen=True)
class ViewportSetMagnifierInternalSplitEvent:
    split_position: float

@dataclass(frozen=True)
class ViewportToggleMagnifierPartEvent:
    part: str
    visible: bool

@dataclass(frozen=True)
class ViewportToggleMagnifierLaserEvent:
    enabled: bool

@dataclass(frozen=True)
class ViewportUpdateMagnifierCombinedStateEvent:
    pass

@dataclass(frozen=True)
class ViewportToggleOrientationEvent:
    is_horizontal: bool

@dataclass(frozen=True)
class ViewportToggleMagnifierOrientationEvent:
    is_horizontal: bool

@dataclass(frozen=True)
class ViewportToggleFreezeMagnifierEvent:
    freeze: bool

@dataclass(frozen=True)
class ViewportOnSliderPressedEvent:
    slider_name: str

@dataclass(frozen=True)
class ViewportOnSliderReleasedEvent:
    slider_name: str
    provider: str | None = None

@dataclass(frozen=True)
class ViewportSetMagnifierVisibilityEvent:
    left: bool
    center: bool
    right: bool

@dataclass(frozen=True)
class ViewportToggleMagnifierEvent:
    enabled: bool
