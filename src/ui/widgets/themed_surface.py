"""Plain QWidget that paints a live theme-token background in paintEvent.

Use for leaf surfaces that must not rely on Qt's setPalette/autoFillBackground
path — see docs/dev/KNOWN_BUGS.md and ThemedBackgroundContainer.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPalette
from PySide6.QtWidgets import QRhiWidget, QWidget

from sli_ui_toolkit.widgets import ThemedWidget
from ui.theming import resolve_theme_color


class ThemedSurface(ThemedWidget, QWidget):
    """QWidget whose background tracks a theme color token via explicit paint."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        color_token: str = "label.image.background",
        opaque: bool = True,
    ):
        self._color_token = color_token
        self._bg_color = QColor()
        super().__init__(parent)
        if opaque:
            self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._bg_color)
        painter.end()

    def on_theme_changed(self) -> None:
        self._bg_color = QColor(
            resolve_theme_color(self._theme_manager, self._color_token)
        )
        super().on_theme_changed()


def apply_qrhi_theme_background(
    widget: QWidget | None,
    theme_manager,
    *,
    color_token: str = "label.image.background",
) -> None:
    """Push a theme background color into a QRhi canvas widget."""
    if widget is None or theme_manager is None:
        return
    bg = resolve_theme_color(theme_manager, color_token)
    pal = widget.palette()
    pal.setColor(widget.backgroundRole(), bg)
    pal.setColor(widget.foregroundRole(), bg)
    pal.setColor(QPalette.ColorRole.Window, bg)
    pal.setColor(QPalette.ColorRole.Base, bg)
    widget.setPalette(pal)
    widget.setAutoFillBackground(True)
    if isinstance(widget, QRhiWidget):
        widget._theme_background_color = QColor(bg)
    widget.update()
