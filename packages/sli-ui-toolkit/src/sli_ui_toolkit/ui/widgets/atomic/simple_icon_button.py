from typing import List, Union

from PyQt6.QtCore import QEvent, QSize
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QPushButton

from sli_ui_toolkit.icons import resolve_icon
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.helpers import UnderlineConfig, draw_bottom_underline
from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style, update_widget_style

class SimpleIconButton(QPushButton):
    def __init__(self, icon, parent=None):
        super().__init__(parent)
        self._icon = icon
        self._current_color = None
        self._variant = "default"
        self._density = "normal"
        self._icon_size_px = 22
        self.setFixedSize(36, 36)
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._update_style)
        self._update_style()

    def set_color(self, color: Union[QColor, List[QColor]]):
        self._current_color = color
        self.update()

    def event(self, event):
        if event.type() == QEvent.Type.DynamicPropertyChange:
            name = event.propertyName().data().decode("utf-8", errors="ignore")
            if name == "variant":
                self._variant = str(self.property("variant") or self._variant)
            elif name == "density":
                self._density = str(self.property("density") or self._density)
            elif name in {"accentColor", "underlineColor"}:
                self._current_color = self.property(name) or self._current_color
            elif name == "iconSizePx":
                self._icon_size_px = max(1, int(self.property("iconSizePx") or self._icon_size_px))
                self._update_style()
                self.updateGeometry()
            update_widget_style(self)
        return super().event(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        style = read_widget_style(self, default_icon_size=self._icon_size_px)
        underline_color = style.underline_color or style.accent_color or self._current_color
        if underline_color is not None:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            alpha = None
            if isinstance(underline_color, QColor):
                alpha = underline_color.alpha()
            config = UnderlineConfig(
                thickness=1.0,
                vertical_offset=1.0,
                arc_radius=2.0,
                alpha=alpha,
                color=underline_color,
            )
            draw_bottom_underline(painter, self.rect(), self.theme_manager, config)
            painter.end()

    def _update_style(self):
        self.setIcon(resolve_icon(self._icon))
        self.setIconSize(QSize(self._icon_size_px, self._icon_size_px))

    def getIconSizePx(self) -> int:
        return int(self._icon_size_px)

    def setIconSizePx(self, size_px: int):
        size_px = max(1, int(size_px))
        if self._icon_size_px != size_px:
            self._icon_size_px = size_px
            self.setProperty("iconSizePx", size_px)
            self._update_style()
            self.updateGeometry()
