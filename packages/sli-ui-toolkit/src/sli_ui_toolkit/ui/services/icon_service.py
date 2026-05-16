import os
from pathlib import Path
from typing import Dict, Type, TypeVar, Union

from PyQt6.QtGui import QIcon

from sli_ui_toolkit.theme import ThemeManager

T = TypeVar("T")

class IconService:
    def __init__(
        self, project_root: str, icons_relative_path: str = "resources/assets/icons"
    ):
        self.project_root = Path(project_root)
        self.icons_path = self.project_root / icons_relative_path
        self._md_cache: Dict[str, Dict[str, QIcon]] = {}

    def get_icon(self, icon_name: str, is_dark: bool = None) -> QIcon:
        if is_dark is None:
            theme_manager = ThemeManager.get_instance()
            is_dark = theme_manager.is_dark()

        if is_dark:
            icon_path = self.icons_path / "dark" / icon_name
        else:
            icon_path = self.icons_path / "light" / icon_name

        try:
            icon_path_str = str(icon_path)
            if not os.path.exists(icon_path_str):
                icon_path = self.icons_path / icon_name
                icon_path_str = str(icon_path)
        except (AttributeError, RecursionError):
            icon_path = self.icons_path / icon_name
            icon_path_str = str(icon_path)

        return QIcon(icon_path_str)

    def get_enum_icon(
        self, icon_enum: Union[str, object], enum_class: Type[T]
    ) -> QIcon:
        if isinstance(icon_enum, str):
            for item in enum_class:
                if item.value == icon_enum:
                    return self.get_icon(item.value)
            raise ValueError(f"Icon '{icon_enum}' not found in {enum_class.__name__}")

        return self.get_icon(icon_enum.value)

_services: Dict[str, IconService] = {}

def get_icon_service(
    project_name: str,
    *,
    project_root: str | None = None,
    icons_relative_path: str = "resources/assets/icons",
) -> IconService:
    if project_name not in _services:
        if project_root is None:
            project_root = str(Path.cwd())
        _services[project_name] = IconService(project_root, icons_relative_path)

    return _services[project_name]

def get_icon_by_name(
    icon_name: str,
    project_name: str = "Default",
    *,
    project_root: str | None = None,
    icons_relative_path: str = "resources/assets/icons",
) -> QIcon:
    service = get_icon_service(
        project_name,
        project_root=project_root,
        icons_relative_path=icons_relative_path,
    )
    return service.get_icon(icon_name)
