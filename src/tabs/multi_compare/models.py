"""Data models for multi-compare session."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

@dataclass
class CompareSlot:
    """One image slot in the grid."""

    id: int
    path: Path | None = None
    label: str = ""
    image: np.ndarray | None = None

    @property
    def is_loaded(self) -> bool:
        return self.image is not None

@dataclass
class GridLayout:
    """Grid dimensions computed from slot count."""

    cols: int
    rows: int

    @staticmethod
    def for_count(n: int) -> "GridLayout":
        if n <= 2:
            return GridLayout(cols=2, rows=1)
        if n <= 4:
            return GridLayout(cols=2, rows=2)
        if n <= 6:
            return GridLayout(cols=3, rows=2)
        if n <= 9:
            return GridLayout(cols=3, rows=3)
        return GridLayout(cols=4, rows=3)

@dataclass
class MultiCompareState:
    """State for the multi-compare view."""

    slots: list[CompareSlot] = field(default_factory=list)
    focused_slot_id: int | None = None
    zoom: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0

    min_slots: int = 3
    max_slots: int = 12

    @property
    def grid(self) -> GridLayout:
        count = len(self.slots) if self.focused_slot_id is None else 1
        return GridLayout.for_count(count)

    @property
    def is_focused(self) -> bool:
        return self.focused_slot_id is not None
