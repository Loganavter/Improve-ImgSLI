from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisSetChannelViewModeEvent:
    mode: str


@dataclass(frozen=True)
class AnalysisSetDiffModeEvent:
    mode: str
