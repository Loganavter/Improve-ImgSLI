from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QStackedWidget, QVBoxLayout, QWidget

from ..atomic.custom_button import CustomButton
from .sidebar_nav_list import SidebarNavList

class DialogActionBar(QWidget):
    def __init__(
        self,
        primary_text: str,
        secondary_text: str = "Cancel",
        *,
        primary_min_size: tuple[int, int] = (100, 32),
        secondary_min_size: tuple[int, int] = (100, 32),
        parent=None,
    ):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addStretch()

        self.primary_button = CustomButton(None, primary_text)
        self.primary_button.setProperty("class", "primary")
        self.primary_button.setMinimumSize(*primary_min_size)

        self.secondary_button = CustomButton(None, secondary_text)
        self.secondary_button.setMinimumSize(*secondary_min_size)

        layout.addWidget(self.primary_button)
        layout.addWidget(self.secondary_button)

class ScrollableDialogPage(QWidget):
    def __init__(
        self,
        *,
        content_margins: tuple[int, int, int, int] = (0, 0, 12, 0),
        content_spacing: int = 15,
        parent=None,
    ):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(*content_margins)
        self.content_layout.setSpacing(content_spacing)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self.scroll_area.setWidget(self.content_widget)
        layout.addWidget(self.scroll_area)

class SidebarDialogShell(QWidget):
    def __init__(
        self,
        *,
        sidebar_width: int = 200,
        content_margins: tuple[int, int, int, int] = (20, 20, 20, 20),
        content_spacing: int = 10,
        parent=None,
    ):
        super().__init__(parent)
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.sidebar = SidebarNavList()
        self.sidebar.setFixedWidth(sidebar_width)

        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(*content_margins)
        self.content_layout.setSpacing(content_spacing)

        self.pages_stack = QStackedWidget()
        self.content_layout.addWidget(self.pages_stack)

        self.main_layout.addWidget(self.sidebar)
        self.main_layout.addWidget(self.content_area, 1)

