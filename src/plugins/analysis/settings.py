from __future__ import annotations

from dataclasses import dataclass

from core.plugin_system.settings import auto_persist

@auto_persist
@dataclass
class AnalysisSettings:
    auto_psnr: bool = True
    auto_ssim: bool = True

