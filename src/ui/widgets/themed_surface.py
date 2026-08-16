"""Plain QWidget that paints a live theme-token background in paintEvent.

Use for leaf surfaces that must not rely on Qt's setPalette/autoFillBackground
path — see docs/dev/KNOWN_BUGS.md and ThemedBackgroundContainer.
"""

from __future__ import annotations

from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

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


class ThemedBackgroundContainer(ThemedSurface):
    """ThemedSurface defaulting to the ``Window`` token — app chrome bars.

    Kept as a thin alias of ThemedSurface (they were duplicate classes) so
    existing chrome call sites keep their intent spelled out.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        color_token: str = "Window",
    ):
        super().__init__(parent, color_token=color_token, opaque=False)


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
        # Opaque clear into a translucent CSD shell — see rhi_render.resolve_clear_color.
        opaque = QColor(bg)
        opaque.setAlpha(255)
        widget._theme_background_color = opaque  # type: ignore[attr-defined]  # dynamic attr
    widget.update()



ThemedSurface.inspect_spec = InspectSpec(
    family="ThemedSurface",
    state=(SpecField("color_token", "_color_token", private=True),),
    docs="docs/dev/widgets/themed_surface.md",
)

ThemedBackgroundContainer.inspect_spec = InspectSpec(
    family="ThemedBackgroundContainer",
    state=(SpecField("color_token", "_color_token", private=True),),
    docs="docs/dev/widgets/themed_surface.md",
)