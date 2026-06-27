from __future__ import annotations

import logging

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QRhiWidget, QWidget

from shared_toolkit.ui.managers.font_manager import FontManager
from ui.theming import resolve_theme_color
from ui.widgets.canvas.helpers import get_canvas

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
        if isinstance(widget, QRhiWidget):
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
        self._apply_widget_background(
            getattr(window.ui, "image_container_widget", None), bg
        )
        self._apply_widget_background(image_label, bg)
        placeholder = getattr(window.ui, "image_startup_placeholder", None)
        if placeholder is not None:
            placeholder.set_background_color(bg)
        for rhi_widget in window.findChildren(QRhiWidget):
            if rhi_widget is image_label:
                continue
            if hasattr(rhi_widget, "apply_theme_background"):
                rhi_widget.apply_theme_background(QColor(bg))
            else:
                rhi_widget._theme_background_color = QColor(bg)
            rhi_widget.update()

    def update_chrome_background(self) -> None:
        """Paint workspace shell and tab pages with the app Window color.

        QWidget children that don't paint a background (toolbars/footers/
        selection rows) inherit visually from their themed page parent, so
        the dark theme reaches every region that isn't the image canvas.
        """
        window = self.window
        if window.ui is None:
            return
        bg = QColor(resolve_theme_color(window.theme_manager, "Window"))
        if not bg.isValid():
            return
        targets = [
            getattr(window.ui, "workspace_stack", None),
            getattr(window.ui, "image_compare_widget", None),
        ]
        stack = getattr(window.ui, "workspace_stack", None)
        if stack is not None:
            for i in range(stack.count()):
                targets.append(stack.widget(i))
        for widget in targets:
            self._apply_widget_background(widget, bg)

    def on_theme_changed(self) -> None:
        window = self.window
        self.update_image_label_background()
        self.update_chrome_background()
        try:
            FontManager.get_instance().apply_from_state(window.store)
            current_font = QApplication.font()
            window.setFont(current_font)
        except Exception as exc:
            logger.error("Error enforcing font style: %s", exc)

        window.style().unpolish(window)
        window.style().polish(window)
        window.update()
