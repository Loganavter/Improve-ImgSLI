from __future__ import annotations

from dataclasses import dataclass

from domain.types import Color


@dataclass(frozen=True)
class SettingsToggleDividerVisibilityEvent:
    visible: bool


@dataclass(frozen=True)
class SettingsSetDividerColorEvent:
    color: Color


@dataclass(frozen=True)
class SettingsSetDividerThicknessEvent:
    thickness: int
