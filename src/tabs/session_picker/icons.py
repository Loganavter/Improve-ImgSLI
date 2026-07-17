"""Session-picker tab icon registry."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from tabs.icon_loader import tab_icon_resolver

_TAB_DIR = Path(__file__).resolve().parent
get_icon = tab_icon_resolver(_TAB_DIR)


class Icon(Enum):
    ADD = "add.svg"
