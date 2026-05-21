from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from sli_ui_toolkit.managers import DelayedActionTimer
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.atomic.tooltips import install_custom_tooltip
from sli_ui_toolkit.ui.widgets.composite.color_options_flyout import IconActionFlyout

class FlyoutIconButton(QWidget):
    primaryTriggered = pyqtSignal()
    actionTriggered = pyqtSignal(str)
    elementHovered = pyqtSignal(str)
    elementHoverEnded = pyqtSignal()

    def __init__(
        self,
        icon,
        *,
        flyout: IconActionFlyout | None = None,
        parent=None,
        button_size: int = 36,
        flyout_show_delay_ms: int = 150,
        flyout_hide_check_delay_ms: int = 120,
        flyout_auto_hide_delay_ms: int = 180,
    ):
        super().__init__(parent)
        self.setFixedSize(button_size, button_size)
        self._tooltip_text = ""
        self._flyout_auto_hide_delay_ms = int(flyout_auto_hide_delay_ms)
        install_custom_tooltip(self)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.button = Button(icon, parent=self)
        self.button.setFixedSize(button_size, button_size)
        self.layout.addWidget(self.button)

        self.flyout = flyout if flyout is not None else IconActionFlyout(self.window())
        self.flyout.hide()
        self.flyout.elementHovered.connect(self.elementHovered.emit)
        self.flyout.elementHoverEnded.connect(self.elementHoverEnded.emit)
        self.flyout.actionTriggered.connect(self._on_flyout_action_triggered)

        self.flyout_timer = DelayedActionTimer(
            self._show_flyout,
            parent=self,
            interval_ms=int(flyout_show_delay_ms),
        )
        self.hide_timer = DelayedActionTimer(
            self._check_and_hide_flyout,
            parent=self,
            interval_ms=int(flyout_hide_check_delay_ms),
        )

        self.button.installEventFilter(self)
        self.flyout.installEventFilter(self)
        self.button.clicked.connect(self._on_button_clicked)

    def setToolTip(self, text: str) -> None:
        self._tooltip_text = str(text or "")
        super().setToolTip(self._tooltip_text)
        self.button.setToolTip(self._tooltip_text)

    def set_flyout(self, flyout: IconActionFlyout) -> None:
        if self.flyout is flyout:
            return
        if self.flyout is not None:
            self.flyout.removeEventFilter(self)
            try:
                self.flyout.actionTriggered.disconnect(self._on_flyout_action_triggered)
            except Exception:
                pass
        self.flyout = flyout
        self.flyout.hide()
        self.flyout.installEventFilter(self)
        self.flyout.elementHovered.connect(self.elementHovered.emit)
        self.flyout.elementHoverEnded.connect(self.elementHoverEnded.emit)
        self.flyout.actionTriggered.connect(self._on_flyout_action_triggered)

    def refresh_visual_state(self):
        if hasattr(self.flyout, "update_state"):
            self.flyout.update_state()

    def _on_button_clicked(self):
        self.primaryTriggered.emit()

    def _on_flyout_action_triggered(self, action_id: str):
        if hasattr(self.flyout, "cancel_auto_hide"):
            self.flyout.cancel_auto_hide()
        self.actionTriggered.emit(action_id)
        self.flyout.hide()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.RightButton:
            self.hide_timer.stop()
            self.flyout_timer.stop()
            self._show_flyout()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self.button.rect().contains(
            event.pos()
        ):
            self._on_button_clicked()
            event.accept()
            return
        super().mousePressEvent(event)

    def eventFilter(self, obj, event):
        if obj is self.button:
            if event.type() == QEvent.Type.Enter:
                self.hide_timer.stop()
                if hasattr(self.flyout, "cancel_auto_hide"):
                    self.flyout.cancel_auto_hide()
                self.flyout_timer.start()
            elif event.type() == QEvent.Type.Leave:
                self.flyout_timer.stop()
                if self.flyout.isVisible():
                    if hasattr(self.flyout, "schedule_auto_hide"):
                        self.flyout.schedule_auto_hide(self._flyout_auto_hide_delay_ms)
                else:
                    self.hide_timer.start()

        if obj is self.flyout:
            if event.type() == QEvent.Type.Enter:
                self.hide_timer.stop()
                if hasattr(self.flyout, "cancel_auto_hide"):
                    self.flyout.cancel_auto_hide()
            elif event.type() == QEvent.Type.Leave:
                if hasattr(self.flyout, "schedule_auto_hide"):
                    self.flyout.schedule_auto_hide(self._flyout_auto_hide_delay_ms)
                else:
                    self.hide_timer.start()

        return super().eventFilter(obj, event)

    def _show_flyout(self):
        if hasattr(self.flyout, "update_state"):
            self.flyout.update_state()
        if hasattr(self.flyout, "cancel_auto_hide"):
            self.flyout.cancel_auto_hide()
        if hasattr(self.flyout, "show_aligned"):
            self.flyout.show_aligned(self, "top")
        else:
            self.flyout.show()

    def _check_and_hide_flyout(self):
        if not self.flyout.isVisible():
            return
        try:
            cursor_pos = self.cursor().pos()
            inside_button = self.rect().contains(self.mapFromGlobal(cursor_pos))
            inside_flyout = self.flyout.contains_global(cursor_pos)
            if not inside_button and not inside_flyout:
                if hasattr(self.flyout, "cancel_auto_hide"):
                    self.flyout.cancel_auto_hide()
                self.flyout.hide()
        except Exception:
            if hasattr(self.flyout, "cancel_auto_hide"):
                self.flyout.cancel_auto_hide()
            self.flyout.hide()

