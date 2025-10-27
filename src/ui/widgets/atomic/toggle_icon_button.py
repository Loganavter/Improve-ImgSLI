
from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import QPushButton

from shared_toolkit.ui.managers.theme_manager import ThemeManager
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
        tm = self.theme_manager

        current_icon = self._icon_checked if super().isChecked() else self._icon_unchecked
        self.setIcon(get_app_icon(current_icon))
        self.setIconSize(QSize(22, 22))

        bg_normal = tm.get_color("button.toggle.background.normal").name()
        bg_hover = tm.get_color("button.toggle.background.hover").name()
        bg_pressed = tm.get_color("button.toggle.background.pressed").name()
        bg_checked = tm.get_color("button.toggle.background.checked").name()
        bg_checked_hover = tm.get_color("button.toggle.background.checked.hover").name()

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
            QPushButton:checked {{
                background-color: {bg_checked};
            }}
            QPushButton:checked:hover {{
                background-color: {bg_checked_hover};
            }}
        """
        self.setStyleSheet(style)

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

