from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from toolkit.managers.theme_manager import ThemeManager

class PathTooltip(QWidget):
    _instance = None
    @classmethod
    def get_instance(cls):
        if cls._instance is None: cls._instance = PathTooltip()
        return cls._instance
    def __init__(self):
        if PathTooltip._instance is not None: raise RuntimeError("Singleton")
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.main_layout = QVBoxLayout(self)
        self.SHADOW_WIDTH = 8
        self.main_layout.setContentsMargins(self.SHADOW_WIDTH, self.SHADOW_WIDTH, self.SHADOW_WIDTH, self.SHADOW_WIDTH)
        self.content_widget = QLabel(self)
        self.content_widget.setObjectName("TooltipContentWidget")
        self.main_layout.addWidget(self.content_widget)
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(self.SHADOW_WIDTH * 2)
        self.shadow.setColor(QColor(0, 0, 0, 100))
        self.shadow.setOffset(1, 2)
        self.content_widget.setGraphicsEffect(self.shadow)
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._apply_style)
        self._apply_style()
    def _apply_style(self):
        self.style().unpolish(self.content_widget)
        self.style().polish(self.content_widget)
        self.update()
    def show_tooltip(self, pos: QPoint, text: str):
        if not text: return
        self.content_widget.setText(text)
        self.adjustSize()
        self.move(pos + QPoint(15, 15))
        self.show()
    def hide_tooltip(self): self.hide()

