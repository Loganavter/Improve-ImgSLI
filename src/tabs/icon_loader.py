"""Tab-local icon resolution helper (not a tab package)."""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Callable

from PySide6.QtGui import QIcon

from sli_ui_toolkit.ui.services.icon_service import IconService


@lru_cache(maxsize=None)
def _cached_service(tab_dir: str) -> IconService:
    return IconService(tab_dir, icons_relative_path="resources/icons")


def tab_icon_resolver(tab_package_dir: Path) -> Callable[[Enum | str], QIcon]:
    """Return ``get_icon(icon) -> QIcon`` rooted at ``<tab>/resources/icons/``."""
    tab_dir = str(tab_package_dir.resolve())

    def get_icon(icon: Enum | str) -> QIcon:
        service = _cached_service(tab_dir)
        if isinstance(icon, Enum):
            return service.get_icon(icon.value)
        return service.get_icon(icon)

    return get_icon
