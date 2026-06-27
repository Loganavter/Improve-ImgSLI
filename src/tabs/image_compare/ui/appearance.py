"""Tab-side appearance handler for the image-compare canvas widgets.

Owns the theme-aware repaint of the image label, image container, startup
placeholder and any QRhiWidget children. The host's ``MainWindowAppearance``
invokes :func:`apply_image_canvas_appearance` from its ``on_theme_changed``
hook so the host does not need to know about image-compare-specific widgets.
"""

from __future__ import annotations

import logging

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QRhiWidget, QWidget

from ui.theming import resolve_theme_color
from ui.widgets.canvas.helpers import get_canvas

logger = logging.getLogger("ImproveImgSLI")


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


def apply_image_canvas_appearance(host_window) -> None:
    theme_manager = getattr(host_window, "theme_manager", None)
    if theme_manager is None:
        return
    bg = resolve_theme_color(theme_manager, "label.image.background")
    _apply_widget_background(
        getattr(host_window, "_startup_placeholder", None), bg
    )
    _apply_widget_background(getattr(host_window, "_startup_cover", None), bg)
    ui = getattr(host_window, "ui", None)
    image_label = get_canvas(ui) if ui is not None else None
    if image_label is None:
        return
    _apply_widget_background(
        getattr(ui, "image_container_widget", None), bg
    )
    _apply_widget_background(image_label, bg)
    placeholder = getattr(ui, "image_startup_placeholder", None)
    if placeholder is not None:
        placeholder.set_background_color(bg)
    for rhi_widget in host_window.findChildren(QRhiWidget):
        if rhi_widget is image_label:
            continue
        if hasattr(rhi_widget, "apply_theme_background"):
            rhi_widget.apply_theme_background(QColor(bg))
        else:
            rhi_widget._theme_background_color = QColor(bg)
        rhi_widget.update()
