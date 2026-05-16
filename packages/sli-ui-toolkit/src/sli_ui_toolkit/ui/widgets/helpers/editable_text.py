from __future__ import annotations

from PyQt6.QtCore import QObject, QEvent, Qt, QTimer
from PyQt6.QtWidgets import QLineEdit, QWidget

class _EditableTextEventFilter(QObject):
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not isinstance(watched, QWidget):
            return super().eventFilter(watched, event)

        if event.type() != QEvent.Type.KeyPress:
            return super().eventFilter(watched, event)

        key = getattr(event, "key", lambda: None)()
        if key not in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            return super().eventFilter(watched, event)

        if isinstance(watched, QLineEdit):
            QTimer.singleShot(0, watched.clearFocus)
            return False

        return super().eventFilter(watched, event)

def apply_editable_text_behavior(widget: QWidget) -> QWidget:
    if getattr(widget, "_editable_text_behavior_installed", False):
        return widget

    behavior = _EditableTextEventFilter(widget)
    widget.installEventFilter(behavior)
    widget._editable_text_behavior = behavior
    widget._editable_text_behavior_installed = True
    return widget
