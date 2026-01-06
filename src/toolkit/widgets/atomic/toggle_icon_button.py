

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import QPushButton

from toolkit.managers.theme_manager import ThemeManager
from ui.icon_manager import AppIcon, get_app_icon

class ToggleIconButton(QPushButton):
    rightClicked = pyqtSignal()
    toggled = pyqtSignal(bool)

    def __init__(self, icon_unchecked: AppIcon, icon_checked: AppIcon = None, parent=None):
        super().__init__(parent)
        self._icon_unchecked = icon_unchecked
        self._icon_checked = icon_checked if icon_checked else icon_unchecked

        self.setCheckable(True)
        self.setFixedSize(36, 36)

        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._update_style)

        self._update_style()
        self.clicked.connect(self._on_clicked)

    def _update_style(self):

        current_icon = self._icon_checked if super().isChecked() else self._icon_unchecked
        self.setIcon(get_app_icon(current_icon))
        self.setIconSize(QSize(22, 22))

    def _on_clicked(self):

        self._update_style()
        self.toggled.emit(super().isChecked())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton and self.rect().contains(event.pos()):
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

