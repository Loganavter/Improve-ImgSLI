from PyQt6.QtCore import QEvent, QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import QPushButton

from sli_ui_toolkit.icons import resolve_icon
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.style_bridge import update_widget_style

class ToggleIconButton(QPushButton):
    rightClicked = pyqtSignal()
    toggled = pyqtSignal(bool)

    def __init__(self, icon_unchecked, icon_checked=None, parent=None):
        super().__init__(parent)
        self._icon_unchecked = icon_unchecked
        self._icon_checked = icon_checked if icon_checked else icon_unchecked
        self._icon_override = None
        self._variant = "default"
        self._density = "normal"
        self._accent_color = None
        self._icon_size_px = 22
        self.setCheckable(True)
        self.setFixedSize(36, 36)
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._update_style)
        self._update_style()
        self.clicked.connect(self._on_clicked)

    def _update_style(self):
        current_icon = self._icon_override or (
            self._icon_checked if super().isChecked() else self._icon_unchecked
        )
        self.setIcon(resolve_icon(current_icon))
        self.setIconSize(QSize(self._icon_size_px, self._icon_size_px))

    def setVisualIconOverride(self, icon):
        if self._icon_override == icon:
            return
        self._icon_override = icon
        self._update_style()

    def _on_clicked(self):
        self._update_style()
        self.toggled.emit(super().isChecked())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton and self.rect().contains(
            event.pos()
        ):
            self.rightClicked.emit()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def isChecked(self) -> bool:
        return super().isChecked()

    def setChecked(self, checked: bool, emit_signal: bool = True):
        old_checked = super().isChecked()
        super().setChecked(checked)
        self._update_style()
        if emit_signal and old_checked != checked:
            self.toggled.emit(checked)

    def event(self, event):
        if event.type() == QEvent.Type.DynamicPropertyChange:
            name = event.propertyName().data().decode("utf-8", errors="ignore")
            if name == "variant":
                self._variant = str(self.property("variant") or self._variant)
            elif name == "density":
                self._density = str(self.property("density") or self._density)
            elif name == "accentColor":
                self._accent_color = self.property("accentColor")
            elif name == "iconSizePx":
                self._icon_size_px = max(1, int(self.property("iconSizePx") or self._icon_size_px))
                self._update_style()
                self.updateGeometry()
            update_widget_style(self)
        return super().event(event)

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

    def getAccentColor(self):
        return self._accent_color

    def setAccentColor(self, color):
        self._accent_color = color
        self.setProperty("accentColor", color)
        update_widget_style(self)

    def getIconSizePx(self) -> int:
        return int(self._icon_size_px)

    def setIconSizePx(self, size_px: int):
        size_px = max(1, int(size_px))
        self._icon_size_px = size_px
        self.setProperty("iconSizePx", size_px)
        self._update_style()
        self.updateGeometry()
