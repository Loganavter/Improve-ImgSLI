"""
Icon Service - Общий сервис для работы с иконками приложений.

Этот модуль предоставляет универсальный API для загрузки иконок
с поддержкой светлой и темной темы через отдельные наборы иконок.
"""

from pathlib import Path
from typing import Dict, Type, TypeVar, Union

from PyQt6.QtGui import QIcon

from src.shared_toolkit.ui.managers.theme_manager import ThemeManager

T = TypeVar('T')

class IconService:
    """
    Универсальный сервис для работы с иконками приложений.

    Поддерживает:
    - Автоматический выбор иконок для светлой и темной темы
    - Отдельные наборы иконок для каждой темы
    - Гибкую настройку путей к ресурсам
    """

    def __init__(self, project_root: str, icons_relative_path: str = "src/resources/assets/icons"):
        """
        Инициализация сервиса иконок.

        Args:
            project_root: Путь к корню проекта
            icons_relative_path: Относительный путь к папке с иконками
        """
        self.project_root = Path(project_root)
        self.icons_path = self.project_root / icons_relative_path
        self._md_cache: Dict[str, Dict[str, QIcon]] = {}

    def get_icon(self, icon_name: str, is_dark: bool = None) -> QIcon:
        """
        Получить иконку по имени файла.

        Args:
            icon_name: Имя файла иконки (например, "settings.svg")
            is_dark: Принудительно указать тему (если None, определяется автоматически)

        Returns:
            QIcon: Обработанная иконка
        """
        if is_dark is None:
            theme_manager = ThemeManager.get_instance()
            is_dark = theme_manager.is_dark()

        if is_dark:
            icon_path = self.icons_path / "dark" / icon_name
        else:
            icon_path = self.icons_path / "light" / icon_name

        if not icon_path.exists():
            icon_path = self.icons_path / icon_name

        return QIcon(str(icon_path))

    def get_enum_icon(self, icon_enum: Union[str, object], enum_class: Type[T]) -> QIcon:
        """
        Получить иконку из enum'а.

        Args:
            icon_enum: Значение enum'а или его строковое представление
            enum_class: Класс enum'а

        Returns:
            QIcon: Обработанная иконка
        """
        if isinstance(icon_enum, str):

            for item in enum_class:
                if item.value == icon_enum:
                    return self.get_icon(item.value)
            raise ValueError(f"Icon '{icon_enum}' not found in {enum_class.__name__}")
        else:

            return self.get_icon(icon_enum.value)

_services: Dict[str, IconService] = {}

def get_icon_service(project_name: str) -> IconService:
    """
    Получить экземпляр IconService для проекта.

    Args:
        project_name: Имя проекта ("Tkonverter" или "Improve-ImgSLI")

    Returns:
        IconService: Экземпляр сервиса для проекта
    """
    if project_name not in _services:

        current_file = Path(__file__).resolve()

        project_root = current_file.parent.parent.parent.parent.parent
        icons_path = "src/resources/assets/icons"

        _services[project_name] = IconService(str(project_root), icons_path)

    return _services[project_name]

def get_icon_by_name(icon_name: str, project_name: str = None) -> QIcon:
    """
    Быстрый способ получить иконку по имени.

    Args:
        icon_name: Имя файла иконки
        project_name: Имя проекта (определяется автоматически если None)

    Returns:
        QIcon: Обработанная иконка
    """
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
