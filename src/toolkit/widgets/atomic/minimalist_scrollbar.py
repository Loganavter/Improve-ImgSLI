

from PyQt6.QtCore import QEvent, QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QScrollArea, QScrollBar

from toolkit.managers.theme_manager import ThemeManager

class MinimalistScrollBar(QScrollBar):

    def __init__(self, orientation=Qt.Orientation.Vertical, parent=None):
        super().__init__(orientation, parent)
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
        if self.theme_manager.is_dark():
            self._idle_color = QColor(255, 255, 255, 60)
            self._hover_color = QColor(255, 255, 255, 90)
        else:
            self._idle_color = QColor(0, 0, 0, 70)
            self._hover_color = QColor(0, 0, 0, 100)
        self.update()

    def paintEvent(self, event):
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

        radius = min(handle_rect.width(), handle_rect.height()) / 2.0
        painter.drawRoundedRect(handle_rect, radius, radius)

    def _get_handle_rect(self):
        if self.minimum() == self.maximum():
            return QRect()

        if self._is_dragging:
            current_thickness = self._drag_thickness
        elif self.underMouse():
            current_thickness = self._hover_thickness
        else:
            current_thickness = self._idle_thickness

        padding = 8
        total_range = self.maximum() - self.minimum() + self.pageStep()
        scroll_range = self.maximum() - self.minimum()

        if total_range <= 0:
            return QRect()

        if self.orientation() == Qt.Orientation.Vertical:
            groove_len = self.height() - padding * 2
            if groove_len <= 0: return QRect()

            handle_len = max((self.pageStep() / total_range) * groove_len, 20)
            track_len = groove_len - handle_len

            handle_pos_rel = ((self.value() - self.minimum()) / scroll_range * track_len) if scroll_range > 0 else 0

            handle_y = handle_pos_rel + padding
            handle_x = (self.width() - current_thickness) // 2

            return QRect(int(handle_x), int(handle_y), int(current_thickness), int(handle_len))
        else:

            groove_len = self.width() - padding * 2
            if groove_len <= 0: return QRect()

            handle_len = max((self.pageStep() / total_range) * groove_len, 20)
            track_len = groove_len - handle_len

            handle_pos_rel = ((self.value() - self.minimum()) / scroll_range * track_len) if scroll_range > 0 else 0

            handle_x = handle_pos_rel + padding
            handle_y = (self.height() - current_thickness) // 2

            return QRect(int(handle_x), int(handle_y), int(handle_len), int(current_thickness))

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        handle_rect = self._get_handle_rect()
        pos_val = event.pos().y() if self.orientation() == Qt.Orientation.Vertical else event.pos().x()
        handle_start = handle_rect.y() if self.orientation() == Qt.Orientation.Vertical else handle_rect.x()

        if handle_rect.contains(event.pos()):
            self._is_dragging = True
            self._drag_start_offset = pos_val - handle_start
            self.update()
            event.accept()
            return

        padding = 8
        handle_len = handle_rect.height() if self.orientation() == Qt.Orientation.Vertical else handle_rect.width()
        track_len = (self.height() if self.orientation() == Qt.Orientation.Vertical else self.width()) - padding * 2 - handle_len

        new_pos_click = pos_val - padding - (handle_len / 2)
        scroll_range = self.maximum() - self.minimum()

        if track_len > 0:
            new_value = self.minimum() + (new_pos_click / track_len) * scroll_range
            self.setValue(int(new_value))

            self._is_dragging = True
            self._drag_start_offset = handle_len / 2
            self.update()

        event.accept()

    def mouseMoveEvent(self, event):
        if self._is_dragging:
            padding = 8
            if self.orientation() == Qt.Orientation.Vertical:
                handle_len = self._get_handle_rect().height()
                track_len = (self.height() - padding * 2) - handle_len
                mouse_pos = event.pos().y()
            else:
                handle_len = self._get_handle_rect().width()
                track_len = (self.width() - padding * 2) - handle_len
                mouse_pos = event.pos().x()

            mouse_pos_in_track = mouse_pos - padding - self._drag_start_offset
            scroll_range = self.maximum() - self.minimum()

            if track_len > 0:
                new_value = self.minimum() + (mouse_pos_in_track / track_len) * scroll_range
                self.setValue(int(new_value))

        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = False
            self.update()
            event.accept()

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)

class OverlayScrollArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.custom_v_scrollbar = MinimalistScrollBar(Qt.Orientation.Vertical, self)
        self._scrollbar_width = 10
        self._scrollbar_gap = 0
        self._stored_items_count = 0
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._delayed_update_scrollbar)

        self.verticalScrollBar().valueChanged.connect(self.custom_v_scrollbar.setValue)
        self.custom_v_scrollbar.valueChanged.connect(self.verticalScrollBar().setValue)

        self.verticalScrollBar().rangeChanged.connect(self.custom_v_scrollbar.setRange)
        self.verticalScrollBar().rangeChanged.connect(lambda *_: self._sync_steps_from_native())

        self.custom_v_scrollbar.setVisible(False)
        self._sync_steps_from_native()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_scrollbar()
        self._sync_steps_from_native()

        self._update_timer.start(10)

    def _delayed_update_scrollbar(self):
        self._update_scrollbar_visibility(self._stored_items_count)

    def _sync_steps_from_native(self):
        native = self.verticalScrollBar()
        try:
            self.custom_v_scrollbar.setPageStep(native.pageStep())
            self.custom_v_scrollbar.setSingleStep(native.singleStep())
        except Exception:
            pass

    def _update_scrollbar_visibility(self, min_items_count=0):
        import logging
        logger = logging.getLogger("ImproveImgSLI")

        if min_items_count > 0:
            self._stored_items_count = min_items_count

        if self.widget():
            content_height = self.widget().height()
            viewport_height = self.viewport().height()
            content_doesnt_fit = content_height > viewport_height

            items_count = min_items_count if min_items_count > 0 else self._stored_items_count

            if items_count == 0:
                need_scrollbar = content_doesnt_fit
            elif items_count <= 8:
                need_scrollbar = False
            else:
                need_scrollbar = content_doesnt_fit

            if need_scrollbar:
                self.setViewportMargins(0, 0, self._scrollbar_width + self._scrollbar_gap, 0)
                self.custom_v_scrollbar.setVisible(True)
            else:
                self.setViewportMargins(0, 0, 0, 0)
                self.custom_v_scrollbar.setVisible(False)

            self._position_scrollbar()

    def _position_scrollbar(self):
        x = self.width() - self._scrollbar_width
        self.custom_v_scrollbar.setGeometry(x, 0, self._scrollbar_width, self.height())
        self.custom_v_scrollbar.raise_()

