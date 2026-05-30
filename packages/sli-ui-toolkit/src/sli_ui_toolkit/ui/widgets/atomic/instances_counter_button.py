from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from sli_ui_toolkit.icons import resolve_icon
from sli_ui_toolkit.theme import ThemeManager

class _SegmentButton(QPushButton):
    wheelScrolled = pyqtSignal(int)

    def wheelEvent(self, event):
        delta = int(event.angleDelta().y())
        if delta:
            self.wheelScrolled.emit(delta)
            event.accept()
            return
        super().wheelEvent(event)

class InstancesCounterButton(QWidget):
    addClicked = pyqtSignal()
    removeClicked = pyqtSignal()
    wheelScrolled = pyqtSignal(int)
    countChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._count = 1
        self._can_remove = False
        self._tooltip_text = ""
        self.setFixedSize(36, 36)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        super().setToolTip("")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._single_button = _SegmentButton("+", self)
        self._single_button.setProperty("counter-segment", True)
        self._single_button.setProperty("segment", "single")
        self._single_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._single_button.setText("")
        self._single_button.setIcon(resolve_icon("add_circle"))
        self._single_button.setIconSize(QSize(20, 20))
        self._single_button.clicked.connect(self.addClicked.emit)
        self._single_button.wheelScrolled.connect(self.wheelScrolled.emit)

        self._add_button = _SegmentButton("+", self)
        self._add_button.setProperty("counter-segment", True)
        self._add_button.setProperty("segment", "top")
        self._add_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._add_button.setText("")
        self._add_button.setIcon(resolve_icon("add"))
        self._add_button.setIconSize(QSize(16, 16))
        self._add_button.clicked.connect(self.addClicked.emit)
        self._add_button.wheelScrolled.connect(self.wheelScrolled.emit)

        self._remove_button = _SegmentButton("-", self)
        self._remove_button.setProperty("counter-segment", True)
        self._remove_button.setProperty("segment", "bottom")
        self._remove_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._remove_button.setText("")
        self._remove_button.setIcon(resolve_icon("remove"))
        self._remove_button.setIconSize(QSize(16, 16))
        self._remove_button.clicked.connect(self._emit_remove_if_allowed)
        self._remove_button.wheelScrolled.connect(self.wheelScrolled.emit)

        layout.addWidget(self._single_button)
        layout.addWidget(self._add_button)
        layout.addWidget(self._remove_button)
        self._update_mode()

        self._theme_manager = ThemeManager.get_instance()
        self._theme_manager.theme_changed.connect(self._refresh_icons)

    def _refresh_icons(self):
        self._single_button.setIcon(resolve_icon("add_circle"))
        self._add_button.setIcon(resolve_icon("add"))
        self._remove_button.setIcon(resolve_icon("remove"))

    def _emit_remove_if_allowed(self):
        if self._can_remove:
            self.removeClicked.emit()

    def setToolTip(self, text):
        self._tooltip_text = str(text or "")
        super().setToolTip(self._tooltip_text)
        self._single_button.setToolTip(self._tooltip_text)
        self._add_button.setToolTip(self._tooltip_text)
        self._remove_button.setToolTip(self._tooltip_text)

    def set_count(self, count: int):
        count = max(1, int(count))
        if self._count != count:
            self._count = count
            self._update_mode()
            self.countChanged.emit(count)

    set_magnifier_count = set_count

    def set_can_remove(self, can_remove: bool):
        can_remove = bool(can_remove)
        if self._can_remove != can_remove:
            self._can_remove = can_remove
            self._remove_button.setEnabled(can_remove)

    def count(self) -> int:
        return self._count

    magnifier_count = count

    def popup_targets(self) -> tuple[QWidget, ...]:
        if self._count > 1:
            return (self._add_button, self._remove_button)
        return (self._single_button,)

    def _update_mode(self):
        split_mode = self._count > 1
        self._single_button.setVisible(not split_mode)
        self._add_button.setVisible(split_mode)
        self._remove_button.setVisible(split_mode)
        self._single_button.setFixedSize(36, 36)
        self._add_button.setFixedHeight(18)
        self._remove_button.setFixedHeight(18)

MagnifierInstancesButton = InstancesCounterButton
