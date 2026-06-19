from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeFlags:
    debug: bool = False
    ui_inspector: bool = False

