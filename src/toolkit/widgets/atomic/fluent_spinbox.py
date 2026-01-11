from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QIntValidator, QFocusEvent
from toolkit.widgets.atomic.custom_line_edit import CustomLineEdit
from toolkit.managers.theme_manager import ThemeManager

class FluentSpinBox(CustomLineEdit):
    valueChanged = pyqtSignal(int)

    def __init__(self, parent=None, default_value: int = 0):
        super().__init__(parent)
        self._minimum = 0
        self._maximum = 100
        self._value = default_value
        self._default_value = default_value

        self.setValidator(QIntValidator(-999999, 999999, self))

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText(str(default_value))

        self.setMinimumWidth(70)
        self.setFixedHeight(33)

        self.editingFinished.connect(self._on_editing_finished)
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._update_style)
        self._update_style()

    def setRange(self, min_val: int, max_val: int):
        self._minimum = min_val
        self._maximum = max_val
        self.setValue(self._value)

    def value(self) -> int:
        return self._value

    def setValue(self, val: int):

        clamped = max(self._minimum, min(self._maximum, int(val)))

        if self._value != clamped:
            self._value = clamped
            self.valueChanged.emit(self._value)

        if self.text() != str(clamped):
            self.setText(str(clamped))

    def _on_editing_finished(self):
        text = self.text().strip()
        try:
            val = int(text) if text else self._default_value
        except ValueError:
            val = self._default_value

        self.setValue(val)

    def wheelEvent(self, event):
        if not self.hasFocus():
            event.ignore()
            return

        delta = event.angleDelta().y()
        if delta == 0:
            return

        step = 1

        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            step = 10

        if delta > 0:
            self.setValue(self._value + step)
        else:
            self.setValue(self._value - step)

        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Up:
            self.setValue(self._value + 1)
            event.accept()
        elif event.key() == Qt.Key.Key_Down:
            self.setValue(self._value - 1)
            event.accept()
        else:
            super().keyPressEvent(event)

    def focusInEvent(self, event: QFocusEvent):

        QTimer.singleShot(0, self.selectAll)
        super().focusInEvent(event)

    def _update_style(self):

        text_color = self.theme_manager.get_color("dialog.text").name()
        self.setStyleSheet(f"color: {text_color};")
        self.update()

