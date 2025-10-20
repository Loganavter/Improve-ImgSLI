"""
Overlay виджет для выбора направления вставки изображения
"""
from PyQt6.QtCore import QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from resources.translations import tr

class PasteDirectionOverlay(QWidget):
    """Overlay виджет с кнопками для выбора направления вставки изображения"""

    direction_selected = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, parent, image_label_widget, is_horizontal=False):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setMouseTracking(True)

        self.image_label_widget = image_label_widget
        self.current_language = "en"
        self.hovered_button = None
        self.is_horizontal = is_horizontal

        self.button_size = 120
        self.spacing = 20
        self.center_size = 60

        self.btn_up_rect = None
        self.btn_down_rect = None
        self.btn_left_rect = None
        self.btn_right_rect = None
        self.btn_cancel_rect = None

    def set_language(self, lang_code: str):
        """Устанавливает язык интерфейса"""
        self.current_language = lang_code
        self.update()

    def showEvent(self, event):
        """При показе устанавливаем геометрию и вычисляем кнопки"""
        super().showEvent(event)

        if self.parent():
            self.setGeometry(self.parent().rect())
        self._update_button_rects()

    def _update_button_rects(self):
        """Обновляет прямоугольники для кнопок по центру image_label"""

        if self.image_label_widget and self.image_label_widget.isVisible():
            image_label_pos = self.image_label_widget.mapTo(self.parent(), self.image_label_widget.rect().topLeft())
            label_center_x = image_label_pos.x() + self.image_label_widget.width() // 2
            label_center_y = image_label_pos.y() + self.image_label_widget.height() // 2
            center_x = label_center_x
            center_y = label_center_y
        else:

            center_x = self.width() // 2
            center_y = self.height() // 2

        if self.is_horizontal:

            self.btn_up_rect = QRect(
                center_x - self.button_size // 2,
                center_y - self.button_size - self.spacing // 2 - self.center_size // 2,
                self.button_size,
                self.button_size
            )

            self.btn_down_rect = QRect(
                center_x - self.button_size // 2,
                center_y + self.spacing // 2 + self.center_size // 2,
                self.button_size,
                self.button_size
            )

            self.btn_left_rect = None
            self.btn_right_rect = None

            self.btn_cancel_rect = QRect(
                center_x - self.center_size // 2,
                center_y - self.center_size // 2,
                self.center_size,
                self.center_size
            )
        else:

            self.btn_left_rect = QRect(
                center_x - self.button_size - self.spacing // 2 - self.center_size // 2,
                center_y - self.button_size // 2,
                self.button_size,
                self.button_size
            )

            self.btn_right_rect = QRect(
                center_x + self.spacing // 2 + self.center_size // 2,
                center_y - self.button_size // 2,
                self.button_size,
                self.button_size
            )

            self.btn_up_rect = None
            self.btn_down_rect = None

            self.btn_cancel_rect = QRect(
                center_x - self.center_size // 2,
                center_y - self.center_size // 2,
                self.center_size,
                self.center_size
            )

    def paintEvent(self, event):
        """Рисует overlay с кнопками"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))

        buttons = []
        if self.btn_up_rect:
            buttons.append((self.btn_up_rect, "up", tr("Вверх", self.current_language)))
        if self.btn_down_rect:
            buttons.append((self.btn_down_rect, "down", tr("Вниз", self.current_language)))
        if self.btn_left_rect:
            buttons.append((self.btn_left_rect, "left", tr("Влево", self.current_language)))
        if self.btn_right_rect:
            buttons.append((self.btn_right_rect, "right", tr("Вправо", self.current_language)))

        for rect, direction, text in buttons:
            is_hovered = self.hovered_button == direction

            if is_hovered:
                bg_color = QColor(255, 255, 255, 230)
                text_color = QColor(0, 0, 0)
                border_color = QColor(100, 150, 255)
                border_width = 3
            else:
                bg_color = QColor(255, 255, 255, 200)
                text_color = QColor(50, 50, 50)
                border_color = QColor(200, 200, 200)
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
            cancel_bg = QColor(220, 220, 220, 200) if is_cancel_hovered else QColor(180, 180, 180, 150)
            painter.setPen(QPen(QColor(100, 100, 100), 2))
            painter.setBrush(cancel_bg)
            painter.drawEllipse(self.btn_cancel_rect)

            painter.setPen(QPen(QColor(80, 80, 80), 2))
            center = self.btn_cancel_rect.center()
            offset = 15
            painter.drawLine(center.x() - offset, center.y() - offset, center.x() + offset, center.y() + offset)
            painter.drawLine(center.x() - offset, center.y() + offset, center.x() + offset, center.y() - offset)

    def mouseMoveEvent(self, event: QMouseEvent):
        """Обрабатывает перемещение мыши для подсветки кнопок"""
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
        """Обрабатывает клик по кнопкам"""
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.pos()

            if self.btn_up_rect and self.btn_up_rect.contains(pos):
                self.direction_selected.emit("up")
                self.hide()
                self.deleteLater()
            elif self.btn_down_rect and self.btn_down_rect.contains(pos):
                self.direction_selected.emit("down")
                self.hide()
                self.deleteLater()
            elif self.btn_left_rect and self.btn_left_rect.contains(pos):
                self.direction_selected.emit("left")
                self.hide()
                self.deleteLater()
            elif self.btn_right_rect and self.btn_right_rect.contains(pos):
                self.direction_selected.emit("right")
                self.hide()
                self.deleteLater()
            elif self.btn_cancel_rect and self.btn_cancel_rect.contains(pos):
                self.cancelled.emit()
                self.hide()
                self.deleteLater()
            else:

                self.cancelled.emit()
                self.hide()
                self.deleteLater()

    def keyPressEvent(self, event):
        """Обрабатывает нажатие клавиш"""
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            self.hide()
            self.deleteLater()
        elif event.key() in (Qt.Key.Key_Up, Qt.Key.Key_W):
            if self.btn_up_rect:
                self.direction_selected.emit("up")
                self.hide()
                self.deleteLater()
        elif event.key() in (Qt.Key.Key_Down, Qt.Key.Key_S):
            if self.btn_down_rect:
                self.direction_selected.emit("down")
                self.hide()
                self.deleteLater()
        elif event.key() in (Qt.Key.Key_Left, Qt.Key.Key_A):
            if self.btn_left_rect:
                self.direction_selected.emit("left")
                self.hide()
                self.deleteLater()
        elif event.key() in (Qt.Key.Key_Right, Qt.Key.Key_D):
            if self.btn_right_rect:
                self.direction_selected.emit("right")
                self.hide()
                self.deleteLater()

