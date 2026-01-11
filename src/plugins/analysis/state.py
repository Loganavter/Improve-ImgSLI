from __future__ import annotations

from dataclasses import dataclass, field

@dataclass
class AnalysisState:

    diff_mode: str = 'off'
    channel_view_mode: str = 'RGB'

    psnr: float | None = None
    ssim: float | None = None
    history: list[tuple[float | None, float | None]] = field(default_factory=list)

