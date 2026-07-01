from __future__ import annotations

from dataclasses import dataclass

from domain.types import Color

@dataclass(frozen=True)
class SettingsChangeLanguageEvent:
    lang_code: str

@dataclass(frozen=True)
class SettingsApplyFontSettingsEvent:
    size: int
    weight: int
    color: Color
    bg_color: Color
    draw_bg: bool
    placement: str
    alpha: int

@dataclass(frozen=True)
class SettingsToggleAutoCropBlackBordersEvent:
    enabled: bool

@dataclass(frozen=True)
class SettingsUIModeChangedEvent:
    ui_mode: str


@dataclass(frozen=True)
class SettingsAnalysisMetricsRequestedEvent:
    payload: dict | None = None
