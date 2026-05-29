from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFontMetrics, QPainter
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from sli_ui_toolkit.theme import ThemeManager

class ToastNotification(QWidget):
    _MARGINS_WITH_ACTION = (12, 10, 12, 10)
    _MARGINS_NO_ACTION = (12, 10, 12, 6)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("ToastNotification")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._on_action = None
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide_and_close)

        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        self.content_widget = QWidget(self)
        self.content_widget.setObjectName("ToastContentWidget")
        self.content_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.main_layout = QVBoxLayout(self.content_widget)
        self.main_layout.setContentsMargins(12, 10, 12, 10)
        self.main_layout.setSpacing(8)

        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.message_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.main_layout.addWidget(self.message_label)

        self.action_row = QFrame(self.content_widget)
        self.action_row_layout = QHBoxLayout(self.action_row)
        self.action_row_layout.setContentsMargins(0, 0, 0, 0)
        self.action_row_layout.setSpacing(0)

        self.action_button = QPushButton()
        self.action_button.hide()
        self.action_button.clicked.connect(self._handle_action_clicked)
        self.action_row_layout.addWidget(self.action_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.action_row_layout.addStretch(1)
        self.action_row.hide()
        self.main_layout.addWidget(self.action_row)
        self.root_layout.addWidget(self.content_widget)

        self.progress_container = QWidget(self)
        self.progress_container.setObjectName("ToastProgressContainer")
        self.progress_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.progress_layout = QVBoxLayout(self.progress_container)
        self.progress_layout.setContentsMargins(12, 0, 12, 10)
        self.progress_layout.setSpacing(0)

        self.progress_bar = QProgressBar(self.progress_container)
        self.progress_bar.setObjectName("ToastProgressBar")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setRange(0, 100)
        self.progress_layout.addWidget(self.progress_bar)
        self.progress_container.hide()
        self.root_layout.addWidget(self.progress_container)

        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._on_theme_changed)
        self._apply_surface_state()

    def _apply_content_layout_state(self):
        if self.action_row.isVisible():
            left, top, right, bottom = self._MARGINS_WITH_ACTION
            self.main_layout.setSpacing(8)
        else:
            left, top, right, bottom = self._MARGINS_NO_ACTION
            self.main_layout.setSpacing(0)
        self.main_layout.setContentsMargins(left, top, right, bottom)

    def _on_theme_changed(self):
        self._repolish_surface_widgets()
        self.adjustSize()

    def _repolish_surface_widgets(self):
        widgets = (self, self.content_widget, self.progress_container, self.progress_bar)
        for widget in widgets:
            style = widget.style()
            style.unpolish(widget)
            style.polish(widget)
            widget.update()

    def _apply_surface_state(self):
        has_progress = not self.progress_container.isHidden()
        self.content_widget.setProperty("hasProgress", has_progress)
        self.progress_container.setProperty("hasProgress", has_progress)
        self._repolish_surface_widgets()

    def show_message(
        self,
        message: str,
        max_width: int,
        duration: int = 3000,
        action_text: str | None = None,
        on_action=None,
        progress: int | None = None,
    ):
        self._on_action = on_action

        if action_text:
            self.action_button.setText(action_text)
            self.action_button.show()
            self.action_row.show()
        else:
            self.action_button.hide()
            self.action_row.hide()
        self._apply_content_layout_state()

        self._set_message_text(message, max_width)
        self._set_progress(progress)
        self.adjustSize()
        self.show()
        self._apply_duration(duration)

    def update_message(
        self,
        new_message: str,
        max_width: int,
        success: bool,
        duration: int = 4000,
        progress: int | None = None,
    ):
        self._apply_content_layout_state()
        self._set_message_text(new_message, max_width)
        self._set_progress(progress)
        self.adjustSize()
        self._apply_duration(duration)

    def _set_message_text(self, message: str, max_width: int):
        safe_max_width = max(180, int(max_width))
        content_margins = self.main_layout.contentsMargins()
        progress_margins = self.progress_layout.contentsMargins()
        button_width = self.action_button.sizeHint().width() if self.action_row.isVisible() else 0
        text_width = max(
            80,
            safe_max_width
            - content_margins.left()
            - content_margins.right()
        )
        font_metrics = QFontMetrics(self.message_label.font())
        lines = message.split("\n") if "\n" in message else [message]
        longest_line_width = max((font_metrics.horizontalAdvance(line) for line in lines), default=0)
        desired_text_width = max(80, min(text_width, longest_line_width + 4))
        desired_toast_width = min(
            safe_max_width,
            max(
                180,
                desired_text_width
                + content_margins.left()
                + content_margins.right()
                + 4,
                button_width
                + content_margins.left()
                + content_margins.right(),
                desired_text_width
                + progress_margins.left()
                + progress_margins.right(),
            ),
        )
        final_text_width = max(
            80,
            desired_toast_width
            - content_margins.left()
            - content_margins.right()
        )

        self.setFixedWidth(desired_toast_width)
        self.content_widget.setFixedWidth(desired_toast_width)
        self.progress_container.setFixedWidth(desired_toast_width)
        self.message_label.setFixedWidth(final_text_width)
        self.message_label.setText(message)
        self.action_row.setFixedWidth(final_text_width)
        self.message_label.updateGeometry()
        self.content_widget.adjustSize()
        self.adjustSize()
        self.updateGeometry()

    def _set_progress(self, progress: int | None):
        if progress is None:
            self.progress_container.hide()
            self._apply_surface_state()
            return

        safe_progress = max(0, min(100, int(progress)))
        self.progress_bar.setValue(safe_progress)
        self.progress_container.show()
        self._apply_surface_state()

    def _apply_duration(self, duration: int):
        self._hide_timer.stop()
        if duration > 0:
            self._hide_timer.start(duration)

    def hide_and_close(self):
        self._hide_timer.stop()
        self.hide()
        self.close()

    def _handle_action_clicked(self):
        try:
            if callable(self._on_action):
                self._on_action()
        finally:
            self.hide_and_close()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        painter.end()
        super().paintEvent(event)

    def mousePressEvent(self, event):
        if self.action_button.isVisible() and self.action_button.geometry().contains(
            event.pos()
        ):
            return super().mousePressEvent(event)
        self.hide_and_close()
        event.accept()

class ToastManager:
    def __init__(self, parent_window, image_label=None):
        self.parent_window = parent_window
        self.image_label = image_label
        self._next_id = 1
        self._toasts: dict[int, ToastNotification] = {}

    def show_toast(
        self,
        message: str,
        *,
        duration: int = 3000,
        action_text: str | None = None,
        on_action=None,
        progress: int | None = None,
        success: bool = False,
    ) -> int:
        toast_id = self._next_id
        self._next_id += 1

        toast_parent = self.image_label or self.parent_window
        toast = ToastNotification(toast_parent)
        toast.setProperty("toastSuccess", bool(success))
        toast.show_message(
            message,
            max_width=self._toast_max_width(),
            duration=duration,
            action_text=action_text,
            on_action=on_action,
            progress=progress,
        )
        self._position_toast(toast)
        toast.show()
        toast.raise_()
        self._toasts[toast_id] = toast
        return toast_id

    def update_toast(
        self,
        toast_id: int,
        message: str,
        *,
        success: bool,
        duration: int = 3000,
        progress: int | None = None,
    ) -> None:
        toast = self._toasts.get(toast_id)
        if toast is None:
            return
        toast.setProperty("toastSuccess", bool(success))
        toast.update_message(
            message,
            max_width=self._toast_max_width(),
            success=success,
            duration=duration,
            progress=progress,
        )
        self._position_toast(toast)
        toast.show()
        toast.raise_()

    def close_toast(self, toast_id: int) -> None:
        toast = self._toasts.pop(toast_id, None)
        if toast is None:
            return
        toast.hide_and_close()

    def _toast_max_width(self) -> int:
        if self.image_label is not None:
            try:
                return max(260, int(self.image_label.width() * 0.42))
            except Exception:
                pass
        if self.parent_window is not None:
            try:
                return max(260, int(self.parent_window.width() * 0.35))
            except Exception:
                pass
        return 360

    def _position_toast(self, toast: ToastNotification) -> None:
        host = toast.parentWidget()
        if host is None:
            return
        try:
            x = 12
            y = 12
            toast.move(x, y)
        except Exception:
            pass
