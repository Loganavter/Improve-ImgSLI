from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from ...icon_manager import AppIcon, get_app_icon

class _MagnifierSegmentButton(QPushButton):
    wheelScrolled = pyqtSignal(int)

    def wheelEvent(self, event):
        delta = int(event.angleDelta().y())
        if delta:
            self.wheelScrolled.emit(delta)
            event.accept()
            return
        super().wheelEvent(event)

class MagnifierInstancesButton(QWidget):
    addClicked = pyqtSignal()
    removeClicked = pyqtSignal()
    wheelScrolled = pyqtSignal(int)
    countChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._magnifier_count = 1
        self._can_remove = False

        self.setFixedSize(36, 36)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        super().setToolTip("")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._single_button = _MagnifierSegmentButton("+", self)
        self._single_button.setProperty("magnifier-segment", True)
        self._single_button.setProperty("segment", "single")
        self._single_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._single_button.setText("")
        self._single_button.setIcon(get_app_icon(AppIcon.ADD_CIRCLE))
        self._single_button.setIconSize(QSize(20, 20))
        self._single_button.clicked.connect(self.addClicked.emit)
        self._single_button.wheelScrolled.connect(self.wheelScrolled.emit)

        self._add_button = _MagnifierSegmentButton("+", self)
        self._add_button.setProperty("magnifier-segment", True)
        self._add_button.setProperty("segment", "top")
        self._add_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._add_button.setText("")
        self._add_button.setIcon(get_app_icon(AppIcon.ADD))
        self._add_button.setIconSize(QSize(16, 16))
        self._add_button.clicked.connect(self.addClicked.emit)
        self._add_button.wheelScrolled.connect(self.wheelScrolled.emit)

        self._remove_button = _MagnifierSegmentButton("-", self)
        self._remove_button.setProperty("magnifier-segment", True)
        self._remove_button.setProperty("segment", "bottom")
        self._remove_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._remove_button.setText("")
        self._remove_button.setIcon(get_app_icon(AppIcon.REMOVE))
        self._remove_button.setIconSize(QSize(16, 16))
        self._remove_button.clicked.connect(self._emit_remove_if_allowed)
        self._remove_button.wheelScrolled.connect(self.wheelScrolled.emit)

        layout.addWidget(self._single_button)
        layout.addWidget(self._add_button)
        layout.addWidget(self._remove_button)

        self._update_mode()

    def _emit_remove_if_allowed(self):
        if self._can_remove:
            self.removeClicked.emit()

    def setToolTip(self, _text):
        super().setToolTip("")

    def set_magnifier_count(self, count: int):
        count = max(1, int(count))
        if self._magnifier_count != count:
            self._magnifier_count = count
            self._update_mode()
            self.countChanged.emit(count)

    def set_can_remove(self, can_remove: bool):
        can_remove = bool(can_remove)
        if self._can_remove != can_remove:
            self._can_remove = can_remove
            self._remove_button.setEnabled(can_remove)

    def magnifier_count(self) -> int:
        return self._magnifier_count

    def popup_targets(self) -> tuple[QWidget, ...]:
        if self._magnifier_count > 1:
            return (self._add_button, self._remove_button)
        return (self._single_button,)

    def _update_mode(self):
        split_mode = self._magnifier_count > 1
        self._single_button.setVisible(not split_mode)
        self._add_button.setVisible(split_mode)
        self._remove_button.setVisible(split_mode)
        if split_mode:
            self._single_button.setFixedSize(36, 36)
            self._add_button.setFixedHeight(18)
            self._remove_button.setFixedHeight(18)
        else:
            self._single_button.setFixedSize(36, 36)
            self._add_button.setFixedHeight(18)
            self._remove_button.setFixedHeight(18)
