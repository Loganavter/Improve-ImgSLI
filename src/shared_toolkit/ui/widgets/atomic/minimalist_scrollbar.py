"""
Minimalist scrollbar with smooth animations and theme support.

Provides a modern, minimalist scrollbar design that responds to
hover and drag states with visual feedback.
"""

from PyQt6.QtCore import QEvent, QRect, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QScrollArea, QScrollBar

from src.shared_toolkit.ui.managers.theme_manager import ThemeManager

class MinimalistScrollBar(QScrollBar):
    """
    Minimalist custom scrollbar with dynamic thickness and colors.

    Features:
    - Thin idle state (4px)
    - Medium hover state (6px)
    - Thick drag state (10px)
    - Smooth color transitions
    - Theme-aware colors
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme_manager = ThemeManager.get_instance()

        self._is_dragging = False
        self._drag_start_offset = 0

        self._idle_thickness = 4
        self._hover_thickness = 6
        self._drag_thickness = 10

        self._idle_color = QColor()
        self._hover_color = QColor()

        self._update_colors()
        self.theme_manager.theme_changed.connect(self._update_colors)

        self.setMouseTracking(True)

    def _update_colors(self):
        """Updates colors based on current theme."""
        if self.theme_manager.is_dark():
            self._idle_color = QColor(255, 255, 255, 60)
            self._hover_color = QColor(255, 255, 255, 90)
        else:
            self._idle_color = QColor(0, 0, 0, 70)
            self._hover_color = QColor(0, 0, 0, 100)
        self.update()

    def paintEvent(self, event):
        """Custom paint event for minimalist rendering."""
        if self.minimum() == self.maximum():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        handle_rect = self._get_handle_rect()
        if handle_rect.isEmpty():
            return

        if self._is_dragging:
            current_color = self.theme_manager.get_color("accent")
        elif self.underMouse():
            current_color = self._hover_color
        else:
            current_color = self._idle_color

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(current_color)
        radius = handle_rect.width() / 2.0
        painter.drawRoundedRect(handle_rect, radius, radius)

    def _get_handle_rect(self):
        """Calculates handle rectangle based on current state."""
        if self.minimum() == self.maximum():
            return QRect()

        if self._is_dragging:
            current_thickness = self._drag_thickness
        elif self.underMouse():
            current_thickness = self._hover_thickness
        else:
            current_thickness = self._idle_thickness

        v_padding = 8
        groove_height = self.height() - v_padding * 2

        total_range = self.maximum() - self.minimum() + self.pageStep()
        if total_range <= 0 or groove_height <= 0:
            return QRect()

        handle_height = max((self.pageStep() / total_range) * groove_height, 20)
        scroll_range = self.maximum() - self.minimum()

        track_height = groove_height - handle_height

        handle_y_relative = (
            (self.value() - self.minimum()) / scroll_range * track_height
            if scroll_range > 0
            else 0
        )
        handle_y = handle_y_relative + v_padding
        handle_x = (self.width() - current_thickness) // 2

        return QRect(
            int(handle_x), int(handle_y), int(current_thickness), int(handle_height)
        )

    def mousePressEvent(self, event):
        """Handles mouse press for dragging or jumping."""
        if event.button() != Qt.MouseButton.LeftButton:
            return

        handle_rect = self._get_handle_rect()

        if handle_rect.contains(event.pos()):

            self._is_dragging = True
            self._drag_start_offset = event.pos().y() - handle_rect.y()
            self.update()
            event.accept()
            return

        v_padding = 8
        handle_height = handle_rect.height()
        track_height = (self.height() - v_padding * 2) - handle_height

        new_y = event.pos().y() - v_padding - (handle_height / 2)

        scroll_range = self.maximum() - self.minimum()
        if track_height > 0:
            new_value = self.minimum() + (new_y / track_height) * scroll_range
            self.setValue(int(new_value))

            self._is_dragging = True
            self._drag_start_offset = handle_height / 2
            self.update()

        event.accept()

    def mouseMoveEvent(self, event):
        """Handles mouse move for dragging."""
        if self._is_dragging:
            v_padding = 8
            handle_height = self._get_handle_rect().height()
            track_height = (self.height() - v_padding * 2) - handle_height

            mouse_pos_in_track = event.pos().y() - v_padding - self._drag_start_offset

            scroll_range = self.maximum() - self.minimum()
            if track_height > 0:
                new_value = (
                    self.minimum() + (mouse_pos_in_track / track_height) * scroll_range
                )
                self.setValue(int(new_value))

        event.accept()

    def mouseReleaseEvent(self, event):
        """Handles mouse release to stop dragging."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = False
            self.update()
            event.accept()

    def enterEvent(self, event):
        """Handles mouse enter for hover effect."""
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Handles mouse leave to reset hover effect."""
        self.update()
        super().leaveEvent(event)

class OverlayScrollArea(QScrollArea):
    """QScrollArea, который использует MinimalistScrollBar в качестве оверлея."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.custom_v_scrollbar = MinimalistScrollBar(self)

        self.verticalScrollBar().valueChanged.connect(self.custom_v_scrollbar.setValue)
        self.custom_v_scrollbar.valueChanged.connect(self.verticalScrollBar().setValue)
        self.verticalScrollBar().rangeChanged.connect(self.custom_v_scrollbar.setRange)

        self.custom_v_scrollbar.setVisible(False)
        self.widget_resized = False

    def setWidget(self, widget):
        super().setWidget(widget)
        if widget:
            widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched == self.widget() and event.type() == QEvent.Type.Resize:
            self._update_scrollbar_visibility()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_scrollbar()
        self._update_scrollbar_visibility()

    def _update_scrollbar_visibility(self):
        if self.widget():
            content_height = self.widget().height()
            viewport_height = self.viewport().height()
            is_visible = content_height > viewport_height
            if self.custom_v_scrollbar.isVisible() != is_visible:
                self.custom_v_scrollbar.setVisible(is_visible)

    def _position_scrollbar(self):
        width = 14
        self.custom_v_scrollbar.setGeometry(
            self.width() - width, 0, width, self.height()
        )
        self.custom_v_scrollbar.raise_()
