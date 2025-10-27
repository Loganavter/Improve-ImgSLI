
import platform
import sys
from pathlib import Path
from typing import Dict, Type, TypeVar, Union

from PyQt6.QtGui import QIcon

from shared_toolkit.ui.managers.theme_manager import ThemeManager

T = TypeVar('T')

class IconService:
    def __init__(self, icons_base_path_or_root=None, icons_relative_path=None, use_old_api=False):
        self.use_old_api = use_old_api

        if use_old_api and icons_base_path_or_root and icons_relative_path:

            self.project_root = Path(icons_base_path_or_root)
            self.icons_path = self.project_root / icons_relative_path
        else:

            self.icons_base_path = icons_base_path_or_root

        self._md_cache: Dict[str, Dict[str, QIcon]] = {}

    def get_icon(self, icon_name: str, is_dark: bool = None) -> QIcon:
        if is_dark is None:
            theme_manager = ThemeManager.get_instance()
            is_dark = theme_manager.is_dark()

        if self.use_old_api:

            if is_dark:
                icon_path = self.icons_path / "dark" / icon_name
            else:
                icon_path = self.icons_path / "light" / icon_name

            if not icon_path.exists():
                icon_path = self.icons_path / icon_name

            return QIcon(str(icon_path))
        else:

            theme_folder = "dark" if is_dark else "light"
            relative_path_themed = f"{self.icons_base_path}/{theme_folder}/{icon_name}"
            from shared_toolkit.utils.paths import resource_path
            absolute_path = resource_path(relative_path_themed)

            if not Path(absolute_path).exists():
                relative_path_fallback = f"{self.icons_base_path}/{icon_name}"
                absolute_path = resource_path(relative_path_fallback)

            return QIcon(absolute_path)

    def get_enum_icon(self, icon_enum: Union[str, object], enum_class: Type[T]) -> QIcon:
        if isinstance(icon_enum, str):
            for item in enum_class:
                if item.value == icon_enum:
                    return self.get_icon(item.value)
            raise ValueError(f"Icon '{icon_enum}' not found in {enum_class.__name__}")
        else:
            return self.get_icon(icon_enum.value)

_services: Dict[str, IconService] = {}

def _use_new_api() -> bool:
    is_windows = platform.system() == "Windows"
    return is_windows

def get_icon_service(project_name: str) -> IconService:
    if project_name not in _services:

        use_new_api = _use_new_api()

        if use_new_api:

            if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):

                icons_base_path = "resources/assets/icons"
            else:

                icons_base_path = "src/resources/assets/icons"

            _services[project_name] = IconService(icons_base_path, use_old_api=False)
        else:

            current_file = Path(__file__).resolve()

            project_root = current_file.parent.parent.parent

            if (project_root.parent / "src" / "resources" / "assets" / "icons").exists():

                project_root = current_file.parent.parent.parent.parent.parent
                icons_path = "src/resources/assets/icons"
            elif (project_root / "resources" / "assets" / "icons").exists():

                icons_path = "resources/assets/icons"
            else:

                project_root = project_root.parent
                icons_path = "resources/assets/icons"

            _services[project_name] = IconService(
                str(project_root),
                icons_path,
                use_old_api=True
            )

    return _services[project_name]

def get_icon_by_name(icon_name: str, project_name: str = None) -> QIcon:
    if project_name is None:
        current_file = Path(__file__).resolve()
        if "Tkonverter" in str(current_file):
            project_name = "Tkonverter"
        elif "Improve-ImgSLI" in str(current_file):
            project_name = "Improve-ImgSLI"
        else:
            project_name = "Default"

    service = get_icon_service(project_name)
    return service.get_icon(icon_name)

