from PyQt6.QtCore import Qt, QPoint, QRect
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtGui import QGuiApplication

from toolkit.managers.theme_manager import ThemeManager
from toolkit.managers.flyout_manager import FlyoutManager

class BaseFlyout(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)

        self.container = QWidget(self)
        self.container.setObjectName("FlyoutContainer")
        self._main_layout.addWidget(self.container)

        self.content_layout = QVBoxLayout(self.container)
        self.content_layout.setContentsMargins(4, 4, 4, 4)
        self.content_layout.setSpacing(4)

        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._apply_base_style)
        self._apply_base_style()

        self.flyout_manager = FlyoutManager.get_instance()
        self.flyout_manager.register_flyout(self)

    def _apply_base_style(self):

        bg = self.theme_manager.get_color("flyout.background").name()
        border = self.theme_manager.get_color("flyout.border").name()

        self.container.setStyleSheet(f"""
            QWidget#FlyoutContainer {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 8px;
            }}
        """)

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)

    def show_aligned(self, anchor_widget: QWidget, position="top", offset=5):

        self.flyout_manager.request_show(self)

        self.adjustSize()

        anchor_pos = anchor_widget.mapToGlobal(QPoint(0, 0))
        anchor_w = anchor_widget.width()
        anchor_h = anchor_widget.height()

        my_w = self.width()
        my_h = self.height()

        target_x = anchor_pos.x() + (anchor_w - my_w) // 2
        target_y = anchor_pos.y()

        if position == "top":

            target_y = anchor_pos.y() - my_h - offset
        elif position == "bottom":
            target_y = anchor_pos.y() + anchor_h + offset

        screen = QGuiApplication.screenAt(anchor_pos)
        if screen:
            geo = screen.availableGeometry()

            target_x = max(geo.left(), target_x)

            target_x = min(geo.right() - my_w, target_x)

            if target_y < geo.top() and position == "top":
                target_y = anchor_pos.y() + anchor_h + offset

        self.move(target_x, target_y)
        self.show()
        self.raise_()

    def hide(self):
        self.flyout_manager.request_hide(self)
        super().hide()

