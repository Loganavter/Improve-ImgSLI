from __future__ import annotations

import logging

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

from shared_toolkit.ui.managers.font_manager import FontManager
from ui.widgets.gl_canvas.helpers import get_canvas

logger = logging.getLogger("ImproveImgSLI")

class MainWindowAppearance:
    def __init__(self, window):
        self.window = window

    def update_image_label_background(self) -> None:
        window = self.window
        bg = window.theme_manager.get_color("label.image.background")
        bg_hex = bg.name(QColor.NameFormat.HexArgb)
        window._startup_placeholder.setStyleSheet(f"background-color: {bg_hex};")
        window._startup_cover.setStyleSheet(f"background-color: {bg_hex};")
        image_label = get_canvas(window.ui) if window.ui is not None else None
        if image_label is None:
            return
        pal = image_label.palette()
        pal.setColor(image_label.backgroundRole(), bg)
        pal.setColor(image_label.foregroundRole(), bg)
        pal.setColor(QPalette.ColorRole.Window, bg)
        pal.setColor(QPalette.ColorRole.Base, bg)
        image_label.setPalette(pal)
        image_label.setStyleSheet(f"background-color: {bg_hex};")
        if hasattr(window.ui, "set_image_startup_placeholder_color"):
            window.ui.set_image_startup_placeholder_color(bg)

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
