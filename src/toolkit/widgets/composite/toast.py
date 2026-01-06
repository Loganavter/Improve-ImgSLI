from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from toolkit.managers.theme_manager import ThemeManager

class ToastNotification(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self.setObjectName("ToastNotification")

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._on_action = None

        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(12, 8, 12, 8)
        self.main_layout.setSpacing(10)

        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.main_layout.addWidget(self.message_label)

        self.action_button = QPushButton()
        self.action_button.hide()
        self.action_button.clicked.connect(self._handle_action_clicked)
        self.main_layout.addWidget(self.action_button)

        self.theme_manager = ThemeManager.get_instance()

        self.theme_manager.theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self):

        self.style().unpolish(self)
        self.style().polish(self)
        self.adjustSize()

    def show_message(self, message: str, max_width: int, duration: int = 3000, action_text: str | None = None, on_action = None):

        self._on_action = on_action

        font_metrics = QFontMetrics(self.message_label.font())
        if "\n" in message:
            lines = message.split("\n")
            lines_elided = [font_metrics.elidedText(line, Qt.TextElideMode.ElideRight, max_width) for line in lines]
            self.message_label.setText("\n".join(lines_elided))
        else:
            elided_text = font_metrics.elidedText(message, Qt.TextElideMode.ElideRight, max_width)
            self.message_label.setText(elided_text)

        if action_text:
            self.action_button.setText(action_text)
            self.action_button.show()
        else:
            self.action_button.hide()

        self.adjustSize()
        self.show()

        if duration > 0:
            QTimer.singleShot(duration, self.hide_and_close)

    def update_message(self, new_message: str, max_width: int, success: bool, duration: int = 4000):
        font_metrics = QFontMetrics(self.message_label.font())
        if "\n" in new_message:
            lines = new_message.split("\n")
            lines_elided = [font_metrics.elidedText(line, Qt.TextElideMode.ElideRight, max_width) for line in lines]
            self.message_label.setText("\n".join(lines_elided))
        else:
            elided_text = font_metrics.elidedText(new_message, Qt.TextElideMode.ElideRight, max_width)
            self.message_label.setText(elided_text)
        self.adjustSize()
        if duration > 0:
            QTimer.singleShot(duration, self.hide_and_close)

    def hide_and_close(self):
        self.hide()
        self.close()

    def _handle_action_clicked(self):
        try:
            if callable(self._on_action):
                self._on_action()
        finally:
            self.hide_and_close()

    def mousePressEvent(self, event):

        if self.action_button.isVisible() and self.action_button.geometry().contains(event.pos()):
            return super().mousePressEvent(event)
        self.hide_and_close()
        event.accept()

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect

class ToastManager(QObject):
    def __init__(self, parent_window: QWidget, image_label_widget: QWidget):
        super().__init__()
        self.parent = parent_window
        self.image_label = image_label_widget
        self.toasts = {}
        self.next_toast_id = 0
        self.spacing = 10

        self.parent.installEventFilter(self)
        if self.image_label is not None:
            self.image_label.installEventFilter(self)

    def show_toast(self, message: str, duration: int = 0, action_text: str | None = None, on_action = None) -> int:
        toast_id = self.next_toast_id
        self.next_toast_id += 1

        toast = ToastNotification(self.parent)
        self.toasts[toast_id] = toast

        max_toast_width = int(self.image_label.width() * 0.4) if self.image_label else 400
        toast.show_message(message, max_toast_width, duration, action_text=action_text, on_action=on_action)

        toast.destroyed.connect(lambda: self.toasts.pop(toast_id, None))

        QTimer.singleShot(0, self._reposition_toasts)
        return toast_id

    def update_toast(self, toast_id: int, new_message: str, success: bool, duration: int = 4000):
        if toast_id in self.toasts:
            max_toast_width = int(self.image_label.width() * 0.4) if self.image_label else 400
            toast = self.toasts[toast_id]

            toast._on_action = None
            toast.action_button.hide()
            toast.update_message(new_message, max_toast_width, success, duration)
            self._reposition_toasts()

    def _reposition_toasts(self):
        if not self.parent:
            return

        anchor_point_in_parent = QPoint(0, 0)
        if self.image_label is not None:
            anchor_point_in_parent = self.image_label.mapTo(self.parent, QPoint(0, 0))

        at_x = anchor_point_in_parent.x() + self.spacing
        at_y = anchor_point_in_parent.y() + self.spacing

        for toast in self.toasts.values():
            if not toast.isVisible():
                continue

            toast.setGeometry(QRect(at_x, at_y, toast.width(), toast.height()))
            toast.raise_()

            at_y += toast.height() + self.spacing

    def eventFilter(self, watched, event):

        if watched in (self.parent, self.image_label) and event.type() in [
            QEvent.Type.Resize,
            QEvent.Type.Move,
            QEvent.Type.Show,
            QEvent.Type.WindowStateChange,
            QEvent.Type.LayoutRequest,
        ]:
            QTimer.singleShot(0, self._reposition_toasts)
        return False

