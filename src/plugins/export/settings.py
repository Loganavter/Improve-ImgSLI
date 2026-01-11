from __future__ import annotations

from dataclasses import dataclass

from core.plugin_system.settings import auto_persist

@auto_persist
@dataclass
class ExportSettings:
    default_format: str = "PNG"
    quality: int = 95
    fill_background: bool = False

