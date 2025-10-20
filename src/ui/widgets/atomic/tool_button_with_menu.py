from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu, QPushButton

from src.shared_toolkit.ui.managers.theme_manager import ThemeManager
from src.shared_toolkit.ui.managers.icon_manager import AppIcon, get_app_icon

class ToolButtonWithMenu(QPushButton):
    """
    Кнопка с иконкой, которая открывает выпадающее меню при нажатии.
    """
    triggered = pyqtSignal(QAction)

    def __init__(self, icon: AppIcon, parent=None):
        super().__init__(parent)
        self._icon = icon
        self._actions = []
        self._current_action = None

        self.setFixedSize(36, 36)
        self.setIcon(get_app_icon(self._icon))
        self.setIconSize(self.size() * 0.6)

        self.menu = QMenu(self)
        self.menu.triggered.connect(self._on_action_triggered)
        self.clicked.connect(self.show_menu)

        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._update_style)

        self._update_style()

    def _update_style(self):
        """Обновляет стиль кнопки и меню"""
        tm = self.theme_manager
        is_dark = tm.is_dark()

        self.setIcon(get_app_icon(self._icon))
        self.setIconSize(self.size() * 0.6)

        bg_normal = tm.get_color("button.toggle.background.normal").name()
        bg_hover = tm.get_color("button.toggle.background.hover").name()
        bg_pressed = tm.get_color("button.toggle.background.pressed").name()

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg_normal};
                border: none;
                border-radius: 6px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {bg_hover};
            }}
            QPushButton:pressed, QPushButton:menu-indicator:open {{
                background-color: {bg_pressed};
            }}
        """)

        menu_bg = tm.get_color("flyout.background").name()
        menu_border = tm.get_color("flyout.border").name()
        menu_text = tm.get_color("dialog.text").name()
        menu_selected_bg = tm.get_color("list_item.background.hover").name()

        self.menu.setStyleSheet(f"""
            QMenu {{
                background-color: {menu_bg};
                border: 1px solid {menu_border};
                border-radius: 6px;
                padding: 4px;
            }}
            QMenu::item {{
                color: {menu_text};
                padding: 6px 20px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {menu_selected_bg};
            }}
            QMenu::separator {{
                height: 1px;
                background: {menu_border};
                margin-left: 5px;
                margin-right: 5px;
            }}
        """)

    def set_actions(self, actions: list[tuple[str, any]]):
        """Устанавливает действия для меню. actions: список кортежей (текст, данные)"""
        self.menu.clear()
        self._actions = []
        for text, data in actions:
            action = QAction(text, self)
            action.setData(data)
            action.setCheckable(True)
            self.menu.addAction(action)
            self._actions.append(action)

    def set_current_by_data(self, data: any):
        """Отмечает текущее действие по его данным"""
        for action in self._actions:
            is_current = (action.data() == data)
            action.setChecked(is_current)
            if is_current:
                self._current_action = action

    def show_menu(self):
        """Показывает меню под кнопкой"""
        self.menu.popup(self.mapToGlobal(QPoint(0, self.height())))

    def _on_action_triggered(self, action: QAction):
        """Обработчик выбора действия в меню"""
        self.set_current_by_data(action.data())
        self.triggered.emit(action)

