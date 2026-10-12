"""Image Gallery tab icon registry."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from tabs.icon_loader import tab_icon_resolver

_TAB_DIR = Path(__file__).resolve().parent
get_icon = tab_icon_resolver(_TAB_DIR)


class Icon(Enum):
    GALLERY = "gallery.svg"
    ANALYZE = "analyze.svg"
    STAR = "star.svg"
    VIEW_GRID = "view_grid.svg"
    VIEW_GRID_INACTIVE = "view_grid_inactive.svg"
    VIEW_LIST = "view_list.svg"
    VIEW_LIST_ACTIVE = "view_list_active.svg"
