"""Theme-derived shelf colors, opaque fills, and rounded-panel painting."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from tabs.session_picker.recent.layout import PANEL_RADIUS
from ui.theming import resolve_theme_color


class OpaqueFillHost(QWidget):
    """Content well that paints its fill explicitly (not palette autofill).

    Bare ``setPalette`` + ``autoFillBackground`` is unreliable under translucent
    CSD parents (see ``docs/dev/KNOWN_BUGS.md``). Do **not** set
    ``WA_OpaquePaintEvent`` here — that flag plus a skipped/disabled update
    punches see-through holes through the window chrome.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fill = QColor(255, 255, 255)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAutoFillBackground(False)

    def set_fill_color(self, color: QColor) -> None:
        fill = QColor(color)
        fill.setAlpha(255)
        # QScrollArea.setWidget can flip autoFillBackground back on — pin it off.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAutoFillBackground(False)
        if self._fill == fill:
            self.update()
            return
        self._fill = fill
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(event.rect(), self._fill)
        painter.end()


class ShelfChrome:
    """Owns the Recent shelf surface colors and paint helpers."""

    def __init__(self) -> None:
        self.panel_bg = QColor(0, 0, 0)
        # Page surface (Window) — used under cards so gaps read as white/dark.
        self.content_bg = QColor(255, 255, 255)

    @staticmethod
    def _opaque_window(theme_manager) -> QColor:
        color = QColor(resolve_theme_color(theme_manager, "Window"))
        if not color.isValid() or color.alpha() == 0:
            color = QColor(255, 255, 255)
        color.setAlpha(255)
        return color

    def update_from_theme(self, theme_manager) -> None:
        base = self._opaque_window(theme_manager)
        self.content_bg = QColor(base)
        if base.lightness() > 140:
            self.panel_bg = base.darker(106)
        else:
            self.panel_bg = base.lighter(118)
        self.panel_bg.setAlpha(255)

    def header_button_bg(self) -> QColor:
        """Opaque chip fill that reads against the rounded shelf in both themes."""
        panel = QColor(self.panel_bg)
        panel.setAlpha(255)
        if panel.lightness() > 140:
            color = panel.lighter(108)
        else:
            color = panel.darker(118)
        color.setAlpha(255)
        return color

    def empty_zone_colors(self, theme_manager) -> dict[str, QColor]:
        panel = QColor(self.panel_bg)
        title = QColor(resolve_theme_color(theme_manager, "WindowText"))
        hint = QColor(title)
        hint.setAlpha(170)
        if panel.lightness() > 140:
            border = panel.darker(130)
            fill = panel.darker(103)
        else:
            border = panel.lighter(150)
            fill = panel.lighter(108)
        fill.setAlpha(255)
        return {"border": border, "title": title, "hint": hint, "fill": fill}

    @staticmethod
    def apply_opaque_widget_fill(widget: QWidget | None, color: QColor) -> None:
        if widget is None:
            return
        fill = QColor(color)
        fill.setAlpha(255)
        # Prefer explicit paint hosts (items_host) over palette autofill.
        set_fill = getattr(widget, "set_fill_color", None)
        if callable(set_fill):
            set_fill(fill)
            return
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        widget.setAutoFillBackground(True)
        palette = widget.palette()
        palette.setColor(widget.backgroundRole(), fill)
        widget.setPalette(palette)

    def apply_opaque_fills(
        self,
        *,
        items_view,
    ) -> None:
        """Opaque Window fill under cards + AA shelf-colored rounded corners."""
        content = QColor(self.content_bg)
        content.setAlpha(255)
        shelf = QColor(self.panel_bg)
        shelf.setAlpha(255)
        items_view.apply_surface_colors(content_bg=content, shelf_bg=shelf)

    def paint_shelf(
        self,
        painter: QPainter,
        *,
        widget: QWidget,
        event_rect,
        theme_manager,
        drag_active: bool,
    ) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Fill the widget rect with the page surface first — otherwise the
        # four corners outside the rounded shelf stay unpainted and show as
        # black through the translucent CSD window after a layout grow.
        page_bg = self._opaque_window(theme_manager)
        painter.fillRect(event_rect, page_bg)
        path = QPainterPath()
        rect = widget.rect().adjusted(0, 0, -1, -1)
        path.addRoundedRect(rect, PANEL_RADIUS, PANEL_RADIUS)
        panel = QColor(self.panel_bg)
        panel.setAlpha(255)
        painter.fillPath(path, panel)
        if drag_active:
            accent = QColor(resolve_theme_color(theme_manager, "accent"))
            fill = QColor(accent)
            fill.setAlpha(36)
            painter.fillPath(path, fill)
            pen = QPen(accent, 2.0)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
