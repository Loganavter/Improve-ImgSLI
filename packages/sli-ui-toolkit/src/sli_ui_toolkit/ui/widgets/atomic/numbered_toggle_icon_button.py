from PyQt6.QtCore import QEvent, QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen

from sli_ui_toolkit.icons import get_named_icon, resolve_icon
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.atomic.toggle_icon_button import ToggleIconButton
from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style, update_widget_style

class NumberedToggleIconButton(ToggleIconButton):
    def __init__(self, number: int, parent=None, icon=None):
        icon = icon if icon is not None else get_named_icon("magnifier")
        super().__init__(icon, icon, parent)
        self._slot_index = int(number)
        self._display_number: int | None = None
        self._variant = "default"
        self._density = "normal"
        self.setCheckable(True)
        self.setFixedSize(28, 28)
        self._theme_manager = ThemeManager.get_instance()
        self._theme_manager.theme_changed.connect(self._on_theme_changed)
        self.setIcon(resolve_icon(icon))
        self.setIconSize(QSize(18, 18))

    def set_number(self, n: int):
        self._slot_index = int(n)
        self.update()

    def set_display_number(self, n: int | None):
        self._display_number = n
        self.update()

    def event(self, event):
        if event.type() == QEvent.Type.DynamicPropertyChange:
            name = event.propertyName().data().decode("utf-8", errors="ignore")
            if name == "variant":
                self._variant = str(self.property("variant") or self._variant)
            elif name == "density":
                self._density = str(self.property("density") or self._density)
            update_widget_style(self)
        return super().event(event)

    def _on_theme_changed(self):
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        style = read_widget_style(self, default_icon_size=18, default_corner_radius=6)

        is_dark = self._theme_manager.is_dark()
        text_color = style.foreground_color or QColor(self._theme_manager.get_color("dialog.text"))
        if self.isChecked():
            text_color.setAlpha(140)

        if self._display_number is not None:
            font = QFont()
            font.setBold(True)
            font.setPixelSize(9)
            painter.setFont(font)
            painter.setPen(text_color)
            text_rect = QRect(self.width() - 12, 1, 10, 10)
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignCenter,
                str(self._display_number),
            )

        if self.isChecked():
            strike_color = QColor("#ff4444") if is_dark else QColor("#cc0000")
            strike_color.setAlpha(180)
            pen = QPen(strike_color, 2)
            painter.setPen(pen)
            painter.drawLine(4, self.height() - 4, self.width() - 4, 4)
        painter.end()

    def getVariant(self) -> str:
        return self._variant

    def setVariant(self, variant: str):
        self._variant = str(variant or "default")
        self.setProperty("variant", self._variant)
        update_widget_style(self)

    def getDensity(self) -> str:
        return self._density

    def setDensity(self, density: str):
        self._density = str(density or "normal")
        self.setProperty("density", self._density)
        update_widget_style(self)
