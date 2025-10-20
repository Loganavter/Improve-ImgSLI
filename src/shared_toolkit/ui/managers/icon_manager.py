"""
Icon Manager - Менеджер иконок для Tkonverter.

Этот модуль содержит только enum с иконками и простую обертку над общим IconService.
"""

from enum import Enum
from PyQt6.QtGui import QIcon

from src.shared_toolkit.ui.services import get_icon_service

class AppIcon(Enum):
    """Иконки, используемые в Improve-ImgSLI."""
    SETTINGS = "settings.svg"
    SAVE = "save_icon.svg"
    FOLDER_OPEN = "folder_open.svg"
    CHART = "chart.svg"
    DOWNLOAD = "download.svg"
    CALENDAR = "calendar.svg"
    HELP = "help.svg"

    PHOTO = "photo_icon.svg"
    SYNC = "sync.svg"
    DELETE = "delete.svg"
    ADD = "add.svg"
    REMOVE = "remove.svg"

    MAGNIFIER = "magnifier.svg"
    FREEZE = "freeze.svg"
    TEXT_FILENAME = "text_filename.svg"
    TEXT_MANIPULATOR = "text-manipulator.svg"
    HIGHLIGHT_DIFFERENCES = "highlight_diff_icon.svg"

    VERTICAL_SPLIT = "vertical_split.svg"
    HORIZONTAL_SPLIT = "horizontal_split.svg"

    DIVIDER_VISIBLE = "divider_visible.svg"
    DIVIDER_HIDDEN = "divider_hidden.svg"
    DIVIDER_COLOR = "divider_color.svg"
    DIVIDER_WIDTH = "divider_width.svg"

def get_app_icon(icon: AppIcon) -> QIcon:
    """
    Получить иконку приложения используя общий IconService.

    Args:
        icon: Enum иконки

    Returns:
        QIcon: Обработанная иконка
    """
    service = get_icon_service("Improve-ImgSLI")

    from src.shared_toolkit.ui.managers.theme_manager import ThemeManager
    theme_manager = ThemeManager.get_instance()
    is_dark = theme_manager.is_dark()
    return service.get_icon(icon.value, is_dark=is_dark)
