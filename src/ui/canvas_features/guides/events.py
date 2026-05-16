from __future__ import annotations

from dataclasses import dataclass

from domain.types import Color

@dataclass(frozen=True)
class SettingsToggleGuidesVisibilityEvent:
    enabled: bool

@dataclass(frozen=True)
class SettingsSetGuidesThicknessEvent:
    thickness: int

@dataclass(frozen=True)
class SettingsSetGuidesColorEvent:
    color: Color
