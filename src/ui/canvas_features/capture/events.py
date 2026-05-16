from __future__ import annotations

from dataclasses import dataclass

from domain.types import Color

@dataclass(frozen=True)
class SettingsToggleCaptureVisibilityEvent:
    visible: bool

@dataclass(frozen=True)
class SettingsSetCaptureColorEvent:
    color: Color
