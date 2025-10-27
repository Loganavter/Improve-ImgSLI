\
\
\
\

from enum import Enum
from PyQt6.QtGui import QIcon

from shared_toolkit.ui.services import get_icon_service

class AppIcon(Enum):
    """Иконки, используемые в Improve-ImgSLI."""
    SETTINGS = "settings.svg"
    SAVE = "save_icon.svg"
    QUICK_SAVE = "quick_save.svg"
    HELP = "help.svg"
    PHOTO = "photo_icon.svg"
    SYNC = "sync.svg"
    DELETE = "delete.svg"
    TEXT_MANIPULATOR = "text-manipulator.svg"
    VERTICAL_SPLIT = "vertical_split.svg"
    HORIZONTAL_SPLIT = "horizontal_split.svg"
    MAGNIFIER = "magnifier.svg"
    FREEZE = "freeze.svg"
    TEXT_FILENAME = "text_filename.svg"
    HIGHLIGHT_DIFFERENCES = "highlight_diff_icon.svg"
    DIVIDER_VISIBLE = "divider_visible.svg"
    DIVIDER_HIDDEN = "divider_hidden.svg"
    DIVIDER_COLOR = "divider_color.svg"
    DIVIDER_WIDTH = "divider_width.svg"
    ADD = "add.svg"
    REMOVE = "remove.svg"
    CHECK = "check.svg"

def get_app_icon(icon: AppIcon) -> QIcon:
    """
    Получить иконку приложения используя общий IconService.

    Args:
        icon: Enum иконки

    Returns:
        QIcon: Обработанная иконка
    """
    service = get_icon_service("Improve-ImgSLI")
    return service.get_icon(icon.value)
