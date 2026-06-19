from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen

from sli_ui_toolkit.i18n import tr
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.overlays.in_window_overlay import (
    TopLevelInWindowOverlay,
)


class PasteDirectionOverlay(TopLevelInWindowOverlay):
    direction_selected = Signal(str)
    cancelled = Signal()

    def __init__(self, parent, image_label_widget, is_horizontal=False):
        super().__init__(
            parent,
            close_on_background=False,
            close_on_escape=True,
            close_on_deactivate=True,
        )
        self.image_label_widget = image_label_widget
        self.current_language = "en"
        self.hovered_button = None
        self.is_horizontal = is_horizontal
        self._direction_emitted = False

        self.button_size = 120
        self.spacing = 20
        self.center_size = 60

        self.btn_up_rect = None
        self.btn_down_rect = None
        self.btn_left_rect = None
        self.btn_right_rect = None
        self.btn_cancel_rect = None

        self.setMouseTracking(True)
        self.dismissed.connect(self._on_dismissed)

    def set_language(self, lang_code: str):
        self.current_language = lang_code
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_button_rects()
        self.update()

    def _on_dismissed(self):
        if not self._direction_emitted:
            self.cancelled.emit()

    def _update_button_rects(self):
        if self.image_label_widget and self.image_label_widget.isVisible():
            image_label_pos = self.image_label_widget.mapTo(
                self.parentWidget(), self.image_label_widget.rect().topLeft()
            )
            center_x = image_label_pos.x() + self.image_label_widget.width() // 2
            center_y = image_label_pos.y() + self.image_label_widget.height() // 2
        else:
            center_x = self.width() // 2
            center_y = self.height() // 2

        if self.is_horizontal:
            self.btn_up_rect = QRect(
                center_x - self.button_size // 2,
                center_y - self.button_size - self.spacing // 2 - self.center_size // 2,
                self.button_size,
                self.button_size,
            )
            self.btn_down_rect = QRect(
                center_x - self.button_size // 2,
                center_y + self.spacing // 2 + self.center_size // 2,
                self.button_size,
                self.button_size,
            )
            self.btn_left_rect = None
            self.btn_right_rect = None
        else:
            self.btn_left_rect = QRect(
                center_x - self.button_size - self.spacing // 2 - self.center_size // 2,
                center_y - self.button_size // 2,
                self.button_size,
                self.button_size,
            )
            self.btn_right_rect = QRect(
                center_x + self.spacing // 2 + self.center_size // 2,
                center_y - self.button_size // 2,
                self.button_size,
                self.button_size,
            )
            self.btn_up_rect = None
            self.btn_down_rect = None

        self.btn_cancel_rect = QRect(
            center_x - self.center_size // 2,
            center_y - self.center_size // 2,
            self.center_size,
            self.center_size,
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))

        buttons = []
        if self.btn_up_rect:
            buttons.append(
                (self.btn_up_rect, "up", tr("common.position.up", self.current_language))
            )
        if self.btn_down_rect:
            buttons.append(
                (
                    self.btn_down_rect,
                    "down",
                    tr("common.position.down", self.current_language),
                )
            )
        if self.btn_left_rect:
            buttons.append(
                (
                    self.btn_left_rect,
                    "left",
                    tr("common.position.left", self.current_language),
                )
            )
        if self.btn_right_rect:
            buttons.append(
                (
                    self.btn_right_rect,
                    "right",
                    tr("common.position.right", self.current_language),
                )
            )

        tm = ThemeManager.get_instance()
        surface = QColor(tm.get_color("flyout.background"))
        text_normal = QColor(tm.get_color("WindowText"))
        border_idle = QColor(tm.get_color("flyout.border"))
        accent = QColor(tm.get_color("accent"))
        separator = QColor(tm.get_color("separator.color"))

        for rect, direction, text in buttons:
            is_hovered = self.hovered_button == direction
            if is_hovered:
                bg_color = QColor(surface)
                bg_color.setAlpha(230)
                text_color = QColor(text_normal)
                border_color = QColor(accent)
                border_width = 3
            else:
                bg_color = QColor(surface)
                bg_color.setAlpha(200)
                text_color = QColor(text_normal)
                border_color = QColor(border_idle)
                border_width = 2

            painter.setPen(QPen(border_color, border_width))
            painter.setBrush(bg_color)
            painter.drawRoundedRect(rect, 10, 10)

            painter.setPen(text_color)
            font = painter.font()
            font.setPointSize(14 if is_hovered else 12)
            font.setBold(is_hovered)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

        if self.btn_cancel_rect:
            is_cancel_hovered = self.hovered_button == "cancel"
            cancel_bg = QColor(separator)
            cancel_bg.setAlpha(200 if is_cancel_hovered else 150)
            painter.setPen(QPen(text_normal, 2))
            painter.setBrush(cancel_bg)
            painter.drawEllipse(self.btn_cancel_rect)

            painter.setPen(QPen(text_normal, 2))
            center = self.btn_cancel_rect.center()
            offset = 15
            painter.drawLine(
                center.x() - offset,
                center.y() - offset,
                center.x() + offset,
                center.y() + offset,
            )
            painter.drawLine(
                center.x() - offset,
                center.y() + offset,
                center.x() + offset,
                center.y() - offset,
            )

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = event.pos()
        old_hovered = self.hovered_button

        if self.btn_up_rect and self.btn_up_rect.contains(pos):
            self.hovered_button = "up"
        elif self.btn_down_rect and self.btn_down_rect.contains(pos):
            self.hovered_button = "down"
        elif self.btn_left_rect and self.btn_left_rect.contains(pos):
            self.hovered_button = "left"
        elif self.btn_right_rect and self.btn_right_rect.contains(pos):
            self.hovered_button = "right"
        elif self.btn_cancel_rect and self.btn_cancel_rect.contains(pos):
            self.hovered_button = "cancel"
        else:
            self.hovered_button = None

        if old_hovered != self.hovered_button:
            self.update()

    def mousePressEvent(self, event: QMouseEvent):
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        if event.button() != Qt.MouseButton.LeftButton:
            self.dismiss()
            event.accept()
            return

        direction = None
        if self.btn_up_rect and self.btn_up_rect.contains(pos):
            direction = "up"
        elif self.btn_down_rect and self.btn_down_rect.contains(pos):
            direction = "down"
        elif self.btn_left_rect and self.btn_left_rect.contains(pos):
            direction = "left"
        elif self.btn_right_rect and self.btn_right_rect.contains(pos):
            direction = "right"

        if direction is not None:
            self._direction_emitted = True
            self.direction_selected.emit(direction)
        self.dismiss()
        event.accept()
