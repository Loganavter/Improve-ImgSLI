"""Wheel counter capability for Button widgets.

Implements scroll-wheel value increment/decrement with optional visual layer.
This is an app-level recipe ported from sli-ui-toolkit 0.2.16 demo.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont

from sli_ui_toolkit.ui.widgets.buttons.capabilities import ButtonCapability
from sli_ui_toolkit.ui.widgets.buttons.layers._base import Layer
from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style


class WheelCounterCapability(ButtonCapability):
    """Scroll-wheel value counter: increment/decrement value on wheel events."""

    def __init__(self, min_value: int, max_value: int, start: int = 0, on_change=None):
        super().__init__()
        self.min_value = min_value
        self.max_value = max_value
        self.value = max(min_value, start)
        self._on_change = on_change
        self._button = None

    def attach(self, button, region_id=None):
        super().attach(button, region_id=region_id)
        self._button = button

    def detach(self, button):
        self._button = None

    def handle_wheel_event(self, event) -> bool:
        delta = event.angleDelta().y()
        if delta == 0:
            return False
        step = 1 if delta > 0 else -1
        new_value = max(self.min_value, min(self.max_value, self.value + step))
        if new_value != self.value:
            self.value = new_value
            if self._on_change is not None:
                self._on_change(new_value)
            if self._button is not None:
                self._button.update()
        event.accept()
        return True


class ValueBelowIconLayer(Layer):
    """Draws the capability's value below the button icon."""

    def __init__(self, capability: WheelCounterCapability):
        self._capability = capability

    def draw(self, ctx, tm) -> None:
        rect = ctx.effective_rect.toAlignedRect()
        style = read_widget_style(ctx.widget)
        font = QFont()
        font.setPixelSize(9)
        font.setBold(True)
        ctx.painter.setFont(font)
        ctx.painter.setPen(style.foreground_color or QColor(tm.get_color("dialog.text")))
        value_h = 12
        value_y = rect.y() + rect.height() - value_h - 1
        ctx.painter.drawText(
            QRect(rect.x(), value_y, rect.width(), value_h),
            Qt.AlignmentFlag.AlignCenter,
            str(self._capability.value),
        )
