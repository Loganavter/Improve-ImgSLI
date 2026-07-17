"""Tab-side appearance handler for the image-compare canvas widgets.

Owns the theme-aware repaint of the image label and image container.
The host's ``MainWindowAppearance`` invokes
:func:`apply_image_canvas_appearance` from its ``on_theme_changed`` hook so
the host does not need to know about image-compare-specific widgets. Other
tabs own their own QRhiWidget repaint via their own ``apply_appearance``.
"""

from __future__ import annotations

import logging

from tabs.image_compare.canvas.helpers import get_canvas
from ui.widgets.themed_surface import apply_qrhi_theme_background

logger = logging.getLogger("ImproveImgSLI")


def apply_image_canvas_appearance(host_window) -> None:
    theme_manager = getattr(host_window, "theme_manager", None)
    if theme_manager is None:
        return
    ui = getattr(host_window, "ui", None)
    image_label = get_canvas(ui) if ui is not None else None
    if image_label is None:
        return
    apply_qrhi_theme_background(
        getattr(ui, "image_container_widget", None),
        theme_manager,
    )
    apply_qrhi_theme_background(image_label, theme_manager)
