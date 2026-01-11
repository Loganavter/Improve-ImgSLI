from __future__ import annotations

from dataclasses import dataclass

from core.plugin_system.settings import auto_persist

@auto_persist
@dataclass
class MagnifierSettings:
    size_ratio: float = 0.2
    capture_ratio: float = 0.1
    visible: bool = True

