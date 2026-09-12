"""Tab-side appearance handler for the image-compare canvas widgets.

Owns the theme-aware repaint of the image label and image container.
The host's ``MainWindowAppearance`` invokes ``ImageCompareTab.apply_appearance``
from its ``on_theme_changed`` hook so the host does not need to know about
image-compare-specific widgets. The canvas lives on the tab-owned widget
(``ImageCompareWidget.image_label``), NOT on ``host_window.ui`` (the main
shell) — always pass it as ``canvas_owner``. Other tabs own their own
QRhiWidget repaint via their own ``apply_appearance``.
"""

from __future__ import annotations

import logging

from tabs.image_compare.canvas.helpers import get_canvas
from ui.widgets.themed_surface import apply_qrhi_theme_background

logger = logging.getLogger("ImproveImgSLI")


def apply_image_canvas_appearance(host_window, canvas_owner=None) -> None:
    theme_manager = getattr(host_window, "theme_manager", None)
    if theme_manager is None:
        return
    if canvas_owner is None:
        # Legacy fallback: very old callers passed a ui already carrying the
        # tab widgets. At runtime host_window.ui is the main shell
        # (Ui_ImageComparisonApp) which has no image_label — the tab passes
        # its own widget explicitly (see ImageCompareTab.apply_appearance).
        canvas_owner = getattr(host_window, "ui", None)
    if canvas_owner is None:
        return
    image_label = get_canvas(canvas_owner)
    if image_label is not None:
        apply_qrhi_theme_background(image_label, theme_manager)
    apply_qrhi_theme_background(
        getattr(canvas_owner, "image_container_widget", None),
        theme_manager,
    )
