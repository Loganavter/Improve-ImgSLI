"""Token-painted surfaces for the video editor dialog.

QSS was retired (2026-08-29); these widgets paint their own chrome from
theme tokens so the dialog keeps its look with an empty application
stylesheet.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QProgressBar, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import ThemedWidget
from ui.theming import try_resolve_theme_color

_PREVIEW_RADIUS_PX = 8
_PROGRESS_RADIUS_PX = 2
_TOOLBAR_HAIRLINE_ALPHA = 51


def _token_color(theme_manager, token: str, fallback: QColor) -> QColor:
    try:
        resolved = try_resolve_theme_color(theme_manager, token)
        if resolved is not None and resolved.isValid():
            return QColor(resolved)
    except Exception:
        pass
    return QColor(fallback)


class VideoPreviewSurface(ThemedWidget, QWidget):
    """Black letterbox surface behind the preview canvas (fallback only)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._surface_color = QColor(self.palette().window().color())
        self._border_color = QColor(self.palette().window().color())
        self._read_colors()

    def _read_colors(self) -> None:
        fallback = self.palette().window().color()
        self._surface_color = _token_color(
            self._theme_manager, "video.preview.background", fallback
        )
        self._border_color = _token_color(
            self._theme_manager, "separator.color", fallback
        )

    def on_theme_changed(self) -> None:
        self._read_colors()
        super().on_theme_changed()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = scaled_px(_PREVIEW_RADIUS_PX)
        painter.setPen(QPen(self._border_color, 1))
        painter.setBrush(self._surface_color)
        painter.drawRoundedRect(
            0.5, 0.5, self.width() - 1, self.height() - 1, radius, radius
        )
        painter.end()


class VideoEditorToolbar(ThemedWidget, QFrame):
    """Toolbar frame with a token-painted top hairline (QSS retired)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._hairline = QColor(self.palette().window().color())
        self._read_hairline()

    def _read_hairline(self) -> None:
        fallback = self.palette().window().color()
        color = _token_color(self._theme_manager, "separator.color", fallback)
        color.setAlpha(_TOOLBAR_HAIRLINE_ALPHA)
        self._hairline = color

    def on_theme_changed(self) -> None:
        self._read_hairline()
        super().on_theme_changed()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setPen(QPen(self._hairline, 1))
        painter.drawLine(0, 0, self.width(), 0)
        painter.end()


class ThemedExportProgressBar(ThemedWidget, QProgressBar):
    """Progress bar painting its track/chunk from theme tokens.

    The chunk turns green when the ``state`` property is ``"success"``.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        fallback = self.palette().window().color()
        self._track_color = QColor(fallback)
        self._chunk_color = QColor(fallback)
        self._success_color = QColor(fallback)
        self._read_colors()

    def _read_colors(self) -> None:
        fallback = self.palette().window().color()
        self._track_color = _token_color(
            self._theme_manager, "surface.background", fallback
        )
        self._chunk_color = _token_color(self._theme_manager, "accent", fallback)
        self._success_color = _token_color(
            self._theme_manager, "progress.success", fallback
        )

    def on_theme_changed(self) -> None:
        self._read_colors()
        super().on_theme_changed()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = scaled_px(_PROGRESS_RADIUS_PX)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._track_color)
        painter.drawRoundedRect(self.rect(), radius, radius)
        maximum = self.maximum() - self.minimum()
        ratio = 0.0 if maximum <= 0 else (self.value() - self.minimum()) / maximum
        if ratio > 0.0:
            chunk = self.rect()
            chunk.setWidth(max(1, int(self.width() * ratio)))
            color = (
                self._success_color
                if self.property("state") == "success"
                else self._chunk_color
            )
            painter.setBrush(color)
            painter.drawRoundedRect(chunk, radius, radius)
        painter.end()