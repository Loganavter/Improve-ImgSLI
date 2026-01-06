from PyQt6.QtCore import QRect, Qt, QSize
from PyQt6.QtGui import QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from toolkit.managers.theme_manager import ThemeManager

class CustomGroupWidget(QWidget):

    def __init__(self, title_text: str = "", parent=None):
        super().__init__(parent)
        self._title_text = title_text
        self._border_radius = 8
        self._border_width = 1

        self._title_left_padding = 12

        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self._content_layout = QVBoxLayout(self)
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self.update)

        self._update_layout_margins()

    def _get_title_metrics(self):
        if not self._title_text:
            return 0, 0
        font = self.font()
        font.setBold(True)
        fm = QFontMetrics(font)
        return fm.horizontalAdvance(self._title_text), fm.height()

    def set_title(self, title: str):
        if self._title_text != title:
            self._title_text = title
            self._update_layout_margins()
            self.updateGeometry()
            self.update()

    def get_title(self):
        return self._title_text

    def _update_layout_margins(self):
        _, title_h = self._get_title_metrics()

        top_margin = int(title_h * 0.8) + 12
        self._content_layout.setContentsMargins(12, top_margin, 12, 12)
        self._content_layout.setSpacing(8)

    def add_widget(self, widget):
        self._content_layout.addWidget(widget)

    def add_layout(self, layout):
        self._content_layout.addLayout(layout)

    def sizeHint(self) -> QSize:

        content_size = self._content_layout.sizeHint()

        title_w, title_h = self._get_title_metrics()

        title_full_width = self._title_left_padding + title_w + 30

        final_w = max(content_size.width(), title_full_width)

        final_h = content_size.height()

        return QSize(final_w, final_h)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        border_color = self.theme_manager.get_color("dialog.border")
        pen = QPen(border_color, self._border_width)
        painter.setPen(pen)

        rect = self.rect()
        title_w, title_h = self._get_title_metrics()

        top_y = int(title_h / 2)

        border_rect = QRect(0, top_y, rect.width() - 1, rect.height() - top_y - 1)
        painter.drawRoundedRect(border_rect, self._border_radius, self._border_radius)

        if self._title_text:

            text_x_start = self._title_left_padding
            text_padding = 4

            clear_rect = QRect(
                text_x_start,
                0,
                title_w + (text_padding * 2),
                title_h
            )

            bg_color = self.theme_manager.get_color("dialog.background")
            painter.fillRect(clear_rect, bg_color)

            font = self.font()
            font.setBold(True)
            painter.setFont(font)

            text_color = self.theme_manager.get_color("dialog.text")
            painter.setPen(text_color)

            draw_rect = QRect(
                text_x_start + text_padding,
                0,
                title_w,
                title_h
            )
            painter.drawText(draw_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._title_text)

class CustomGroupBuilder:
    @staticmethod
    def create_styled_group(title_text: str):
        group_widget = CustomGroupWidget(title_text)
        content_layout = group_widget._content_layout

        class TitleWidget:
            def __init__(self, group_widget):
                self._group = group_widget
            def setText(self, text):
                self._group.set_title(text)
            def text(self):
                return self._group.get_title()

        title_widget = TitleWidget(group_widget)
        return group_widget, content_layout, title_widget

