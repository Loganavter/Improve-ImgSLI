
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QPushButton

from shared_toolkit.ui.managers.theme_manager import ThemeManager
from shared_toolkit.ui.widgets.helpers.underline_painter import (
    UnderlineConfig,
    draw_bottom_underline,
)
from ui.icon_manager import AppIcon, get_app_icon

class SimpleIconButton(QPushButton):

    def __init__(self, icon: AppIcon, parent=None):
        super().__init__(parent)
        self._icon = icon
        self._current_color = None

        self.setFixedSize(36, 36)

        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._update_style)

        self._update_style()

    def set_color(self, color: QColor):
        self._current_color = color
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)

        if self._current_color is not None:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            config = UnderlineConfig(
                thickness=1.5,
                vertical_offset=1.5,
                arc_radius=2.0,
                alpha=None,
                color=self._current_color
            )

            draw_bottom_underline(painter, self.rect(), self.theme_manager, config)
            painter.end()

    def _update_style(self):
        self.setIcon(get_app_icon(self._icon))
        self.setIconSize(QSize(22, 22))

        is_dark = self.theme_manager.is_dark()

        if is_dark:
            bg_normal = "#3c3c3c"
            bg_hover = "#4a4a4a"
            bg_pressed = "#353535"
        else:
            bg_normal = "#f0f0f0"
            bg_hover = "#e6e6e6"
            bg_pressed = "#dcdcdc"

        style = f"""
            QPushButton {{
                background-color: {bg_normal};
                border: none;
                border-radius: 6px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {bg_hover};
            }}
            QPushButton:pressed {{
                background-color: {bg_pressed};
            }}
        """
        self.setStyleSheet(style)

