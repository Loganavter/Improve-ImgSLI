"""Session-picker tab icon registry."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from tabs.icon_loader import tab_icon_resolver

_TAB_DIR = Path(__file__).resolve().parent
get_icon = tab_icon_resolver(_TAB_DIR)


class Icon(Enum):
    ADD = "add.svg"
    VIEW_GRID = "view_grid.svg"
    VIEW_LIST = "view_list.svg"
    SORT_ASC = "sort_asc.svg"
    SORT_DESC = "sort_desc.svg"
    SORT_BY_MODIFIED = "sort_by_modified.svg"
    SORT_BY_CREATED = "sort_by_created.svg"
    SORT_BY_NAME = "sort_by_name.svg"
    MISSING_WARNING = "missing_warning.svg"
