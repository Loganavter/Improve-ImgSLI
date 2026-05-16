from __future__ import annotations

from dataclasses import dataclass

from domain.types import Color

@dataclass(frozen=True)
class SettingsToggleMagnifierDividerVisibilityEvent:
    visible: bool

@dataclass(frozen=True)
class SettingsSetMagnifierDividerColorEvent:
    color: Color

@dataclass(frozen=True)
class SettingsSetMagnifierDividerThicknessEvent:
    thickness: int

@dataclass(frozen=True)
class SettingsSetMagnifierBorderColorEvent:
    color: Color
