from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QPushButton
from typing import Union, List

from toolkit.managers.theme_manager import ThemeManager
from toolkit.widgets.helpers.underline_painter import (
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

    def set_color(self, color: Union[QColor, List[QColor]]):
        self._current_color = color
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)

        if self._current_color is not None:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            alpha = self._current_color.alpha() if isinstance(self._current_color, QColor) else 255

            config = UnderlineConfig(
                thickness=1.0,
                vertical_offset=1.0,
                arc_radius=2.0,
                alpha=alpha,
                color=self._current_color
            )

            draw_bottom_underline(painter, self.rect(), self.theme_manager, config)
            painter.end()

    def _update_style(self):
        self.setIcon(get_app_icon(self._icon))
        self.setIconSize(QSize(22, 22))

