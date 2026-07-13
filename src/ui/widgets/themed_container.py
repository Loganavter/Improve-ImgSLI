"""Plain QWidget that paints itself with a live theme-token background.

Replaces the "rely on an ancestor's autoFillBackground to bleed through a
transparent child" trick — see docs/dev/THEMING.md ("Repaint on theme
change: the ThemedWidget mixin").
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget
from sli_ui_toolkit.widgets import ThemedWidget

from ui.theming import resolve_theme_color


class ThemedBackgroundContainer(ThemedWidget, QWidget):
    """QWidget whose background tracks a theme color token."""

    def __init__(self, parent: QWidget | None = None, *, color_token: str = "Window"):
        self._color_token = color_token
        super().__init__(parent)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._bg_color)
        painter.end()

    def on_theme_changed(self) -> None:
        self._bg_color = QColor(resolve_theme_color(self._theme_manager, self._color_token))
        super().on_theme_changed()
