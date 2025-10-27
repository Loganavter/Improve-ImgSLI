import os
from functools import lru_cache

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap

from .theme_manager import ThemeManager

@lru_cache(maxsize=128)
def get_themed_icon(path_to_icon: str, is_dark: bool) -> QIcon:
    """
    Get icon with theme-aware color inversion.

    Args:
        path_to_icon: Full path to the icon file
        is_dark: Whether the current theme is dark

    Returns:
        QIcon: The processed icon
    """
    if not path_to_icon or not os.path.exists(path_to_icon):
        return QIcon()

    source_icon = QIcon(path_to_icon)

    if not is_dark:
        return source_icon

    base_size = source_icon.actualSize(QSize(256, 256))
    if not base_size.isValid():
        base_size = QSize(256, 256)

    source_pixmap = source_icon.pixmap(base_size)
    if source_pixmap.isNull():
        return source_icon

    result_pixmap = QPixmap(source_pixmap.size())
    result_pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(result_pixmap)
    painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
    painter.drawPixmap(0, 0, source_pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(result_pixmap.rect(), QColor("white"))
    painter.end()

    return QIcon(result_pixmap)

def get_icon_by_path(icon_path: str) -> QIcon:
    """
    Get icon with automatic theme-aware color inversion.

    Args:
        icon_path: Path to the icon file

    Returns:
        QIcon: The processed icon
    """
    theme_manager = ThemeManager.get_instance()
    return get_themed_icon(icon_path, theme_manager.is_dark())
