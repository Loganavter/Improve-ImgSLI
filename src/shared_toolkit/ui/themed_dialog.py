"""App-side QDialog base that unifies theme repaint for modal windows.

Folds the copy-pasted ``theme_changed -> polish_themed_dialog + defer geometry``
pattern used across settings/export/image_properties/video_editor into one
non-optional mixin hook. See docs/dev/THEMING.md ("Repaint on theme change").
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog

from shared_toolkit.ui.layout_sizing import defer_dialog_geometry
from sli_ui_toolkit.widgets import ThemedWidget
from ui.theming import polish_themed_dialog


class ThemedDialog(ThemedWidget, QDialog):
    """QDialog that auto-repolishes QSS and defers geometry on theme change."""

    def __init__(self, *args, **kwargs):
        self._theme_ui_ready = False
        super().__init__(*args, **kwargs)

    def mark_theme_ui_ready(self) -> None:
        """Call once the dialog widget tree is built."""
        self._theme_ui_ready = True
        self.on_theme_changed()

    def polish_themed(self) -> None:
        polish_themed_dialog(self._theme_manager, self)

    def install_dialog_geometry(self, apply_geometry) -> None:
        self._apply_dialog_geometry = apply_geometry
        defer_dialog_geometry(self, apply_geometry)

    def on_theme_changed(self) -> None:
        if not self._theme_ui_ready:
            return
        self.polish_themed()
        super().on_theme_changed()
        apply_geometry = getattr(self, "_apply_dialog_geometry", None)
        if callable(apply_geometry):
            defer_dialog_geometry(self, apply_geometry)
        self.on_dialog_theme_changed()

    def on_dialog_theme_changed(self) -> None:
        """Override for dialog-specific theme side effects after the UI exists."""
