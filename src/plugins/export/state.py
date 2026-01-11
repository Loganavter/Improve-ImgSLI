from __future__ import annotations

from dataclasses import dataclass, field

@dataclass
class ExportState:
    last_export_path: str | None = None
    history: list[str] = field(default_factory=list)

