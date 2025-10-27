"""
Custom group widget with custom border drawing.

Provides dynamic border updates and title rendering
with theme-aware styling capabilities.
"""

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from shared_toolkit.ui.managers.theme_manager import ThemeManager

class CustomGroupWidget(QWidget):
    """
    Custom group widget with custom border drawing.

    Features:
    - Custom rounded border
    - Title positioned on border
    - Theme-aware colors
    - Dynamic content layout
    """

    def __init__(self, title_text: str = "", parent=None):
        super().__init__(parent)
        self._title_text = title_text
        self._border_radius = 8
        self._border_width = 1
        self._title_padding = 10

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._content_layout = QVBoxLayout(self)
        self._setup_layout()

        self.setMinimumHeight(60)

        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self.update)

    def _setup_layout(self):
        """Sets up layout considering space for title."""
        title_height = self._get_title_height()
        self._content_layout.setContentsMargins(10, title_height // 2 + 10, 10, 10)
        self._content_layout.setSpacing(6)

    def _get_title_height(self):
        """Returns title height considering boldness."""
        if not self._title_text:
            return 0
        font = self.font()
        font.setBold(True)
        font_metrics = QFontMetrics(font)
        return font_metrics.height()

    def _get_title_width(self):
        """Returns title width considering boldness."""
        if not self._title_text:
            return 0
        font = self.font()
        font.setBold(True)
        font_metrics = QFontMetrics(font)
        return font_metrics.horizontalAdvance(self._title_text)

    def set_title(self, title: str):
        """Sets new title and updates layout."""
        if self._title_text != title:
            self._title_text = title
            self._update_layout_margins()
            self.update()
            self.updateGeometry()
            if self.parent() and self.parent().layout():
                self.parent().layout().invalidate()

    def get_title(self):
        """Returns current title."""
        return self._title_text

    def _update_layout_margins(self):
        """Updates layout margins based on title height."""
        title_height = self._get_title_height()
        self._content_layout.setContentsMargins(10, title_height // 2 + 10, 10, 10)

    def add_widget(self, widget):
        """Adds widget to content layout."""
        self._content_layout.addWidget(widget)

    def add_layout(self, layout):
        """Adds layout to content layout."""
        self._content_layout.addLayout(layout)

    def paintEvent(self, event):
        """Custom paint event for border and title."""
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        border_color = self.theme_manager.get_color("dialog.border")
        pen = QPen(border_color, self._border_width)
        painter.setPen(pen)

        rect = self.rect()
        title_height = self._get_title_height()
        title_width = self._get_title_width()

        border_rect = QRect(
            0,
            title_height // 2,
            rect.width() - 1,
            rect.height() - title_height // 2 - 1
        )
        painter.drawRoundedRect(border_rect, self._border_radius, self._border_radius)

        if self._title_text:

            title_horz_padding = 3

            title_bg_rect = QRect(
                self._title_padding,
                0,
                title_width + 2 * title_horz_padding,
                title_height
            )

            bg_color = self.theme_manager.get_color("dialog.background")
            painter.fillRect(title_bg_rect, bg_color)

            text_rect = QRect(
                self._title_padding + title_horz_padding,
                0,
                title_width,
                title_height
            )

            font = self.font()
            font.setBold(True)
            painter.setFont(font)

            text_color = self.theme_manager.get_color("dialog.text")
            painter.setPen(text_color)
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self._title_text
            )

class CustomGroupBuilder:
    """Helper class for creating styled groups with simplified API."""

    @staticmethod
    def create_styled_group(title_text: str):
        """
        Creates a styled group widget with title.

        Returns:
            tuple: (group_widget, content_layout, title_widget)
        """
        group_widget = CustomGroupWidget(title_text)
        content_layout = group_widget._content_layout

        class TitleWidget:
            """Wrapper for title operations."""
            def __init__(self, group_widget):
                self._group = group_widget

            def setText(self, text):
                self._group.set_title(text)

            def text(self):
                return self._group.get_title()

            def _update_group_size(self):
                self._group.updateGeometry()

        title_widget = TitleWidget(group_widget)
        return group_widget, content_layout, title_widget

