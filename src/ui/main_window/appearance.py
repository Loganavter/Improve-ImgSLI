from __future__ import annotations

import logging

from shared_toolkit.ui.layout_sizing import defer_dialog_geometry
from ui.layout_geometry import apply_main_window_minimum

logger = logging.getLogger("ImproveImgSLI")


class MainWindowAppearance:
    def __init__(self, window):
        self.window = window

    def update_image_label_background(self) -> None:
        window = self.window
        if window.ui is None:
            return
        registry = getattr(window.ui, "_tab_registry", None)
        if registry is not None:
            registry.apply_appearance(window)

    def on_theme_changed(self) -> None:
        window = self.window
        self.update_image_label_background()
        try:
            from shared_toolkit.ui.managers.font_manager import FontManager
            from PySide6.QtWidgets import QApplication

            FontManager.get_instance().apply_from_state(window.store)
            current_font = QApplication.font()
            window.setFont(current_font)
            try:
                from sli_ui_toolkit.managers import UiFont

                UiFont.get_instance().set_family(current_font.family() or None)
                UiFont.get_instance().sync_from_application()
            except Exception:
                pass
        except Exception as exc:
            logger.error("Error enforcing font style: %s", exc)

        defer_dialog_geometry(window, lambda: apply_main_window_minimum(window))

        window.style().unpolish(window)
        window.style().polish(window)
        window.update()
