"""Backward-compatibility wrapper for Button with scroll-wheel value support.

Post-0.2.16: Button no longer has built-in scrollable= support.
This provides a thin compatibility layer for code that still calls get_value()/set_value().
The actual wheel event handling is left as TODO for proper implementation via WheelCounterCapability.
"""

from __future__ import annotations

from PySide6.QtCore import Signal

from sli_ui_toolkit.widgets import Button


class ScrollableCompatButton(Button):
    """Button with backward-compat get_value/set_value/valueChanged API.

    Stores a value internally but does NOT yet implement wheel-counter behavior.
    Wheel events are ignored (left as TODO for WheelCounterCapability migration).
    """

    valueChanged = Signal(int)

    def __init__(self, *args, min_value: int = 0, max_value: int = 10, start: int = 0, **kwargs):
        # Remove old scrollable= kwarg if present (for compat with old code that passes it)
        kwargs.pop('scrollable', None)
        kwargs.pop('underline_visible_when', None)
        super().__init__(*args, **kwargs)
        self.min_value = min_value
        self.max_value = max_value
        self._value = max(min_value, start)
        self._saved_value: int | None = None

    def get_value(self) -> int:
        """Backward-compat: return stored value."""
        return self._value

    def set_value(self, value: int, emit: bool = True) -> None:
        """Backward-compat: set value and optionally emit valueChanged signal."""
        clamped = max(self.min_value, min(self.max_value, value))
        if clamped != self._value:
            self._value = clamped
            if emit:
                self.valueChanged.emit(clamped)

    def get_saved_value(self) -> int:
        """Backward-compat alias for get_value()."""
        return self.get_value()

    def set_saved_value(self, value: int) -> None:
        """Backward-compat: set value without emitting signal."""
        self.set_value(value, emit=False)
        self._saved_value = value

    def restore_saved_value(self) -> int | None:
        """Backward-compat: return the last saved value (without changing current value)."""
        return self._saved_value
