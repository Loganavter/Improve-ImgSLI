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
        # Visible-tab canvas/chrome only — hidden pages flush on session switch.
        # Do not re-apply fonts or polish the whole window here: fonts are
        # theme-independent, and ThemeManager already polished during QSS apply.
        self.update_image_label_background()
        defer_dialog_geometry(self.window, lambda: apply_main_window_minimum(self.window))
