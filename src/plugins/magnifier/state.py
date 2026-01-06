from __future__ import annotations

from dataclasses import dataclass, field

@dataclass
class MagnifierState:
    ids: list[str] = field(default_factory=list)

