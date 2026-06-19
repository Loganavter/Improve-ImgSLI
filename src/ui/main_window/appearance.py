from __future__ import annotations

import logging

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import QApplication, QWidget

from shared_toolkit.ui.managers.font_manager import FontManager
from ui.theming import resolve_theme_color
from ui.widgets.gl_canvas.helpers import get_canvas

logger = logging.getLogger("ImproveImgSLI")

class MainWindowAppearance:
    def __init__(self, window):
        self.window = window

    @staticmethod
    def _apply_widget_background(widget: QWidget | None, bg) -> None:
        if widget is None:
            return
        pal = widget.palette()
        pal.setColor(widget.backgroundRole(), bg)
        pal.setColor(widget.foregroundRole(), bg)
        pal.setColor(QPalette.ColorRole.Window, bg)
        pal.setColor(QPalette.ColorRole.Base, bg)
        widget.setPalette(pal)
        widget.setAutoFillBackground(True)
        if isinstance(widget, QOpenGLWidget):
            widget._theme_background_color = QColor(bg)
        widget.update()

    def update_image_label_background(self) -> None:
        window = self.window
        bg = resolve_theme_color(window.theme_manager, "label.image.background")
        self._apply_widget_background(getattr(window, "_startup_placeholder", None), bg)
        self._apply_widget_background(getattr(window, "_startup_cover", None), bg)
        image_label = get_canvas(window.ui) if window.ui is not None else None
        if image_label is None:
            return
        self._apply_widget_background(getattr(window.ui, "image_container_widget", None), bg)
        self._apply_widget_background(image_label, bg)
        placeholder = getattr(window.ui, "image_startup_placeholder", None)
        if placeholder is not None:
            placeholder.set_background_color(bg)
        for gl_widget in window.findChildren(QOpenGLWidget):
            if gl_widget is image_label:
                continue
            gl_widget._theme_background_color = QColor(bg)
            gl_widget.update()

    def on_theme_changed(self) -> None:
        window = self.window
        self.update_image_label_background()
        try:
            FontManager.get_instance().apply_from_state(window.store)
            current_font = QApplication.font()
            window.setFont(current_font)
        except Exception as exc:
            logger.error("Error enforcing font style: %s", exc)

        window.style().unpolish(window)
        window.style().polish(window)
        window.update()
