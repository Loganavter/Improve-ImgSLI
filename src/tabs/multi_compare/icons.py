"""Multi-compare tab icon registry."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from tabs.icon_loader import tab_icon_resolver

_TAB_DIR = Path(__file__).resolve().parent
get_icon = tab_icon_resolver(_TAB_DIR)


class Icon(Enum):
    GRID = "grid.svg"
    PHOTO = "photo_icon.svg"
    DIVIDER_VISIBLE = "divider_visible.svg"
    DIVIDER_HIDDEN = "divider_hidden.svg"
    DIVIDER_COLOR = "divider_color.svg"
    TEXT_FILENAME = "text_filename.svg"
    SAVE = "save_icon.svg"
    QUICK_SAVE = "quick_save.svg"
    SETTINGS = "settings.svg"
    HELP = "help.svg"
    TEXT_MANIPULATOR = "text-manipulator.svg"
    ADD = "add.svg"
    DELETE = "delete.svg"
    SYNC = "sync.svg"
