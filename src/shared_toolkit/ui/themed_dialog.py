"""App-side QDialog base that unifies theme repaint for modal windows.

Folds the copy-pasted ``theme_changed -> polish_themed_dialog + defer geometry``
pattern used across settings/export/image_properties/video_editor into one
non-optional mixin hook. See docs/dev/THEMING.md ("Repaint on theme change").
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QDialog

from shared_toolkit.ui.layout_sizing import defer_dialog_geometry
from sli_ui_toolkit.widgets import ThemedWidget
from ui.theming import polish_themed_dialog, try_resolve_theme_color


class ThemedDialog(ThemedWidget, QDialog):
    """QDialog that auto-repolishes QSS and defers geometry on theme change."""

    def __init__(self, *args, **kwargs):
        self._theme_ui_ready = False
        super().__init__(*args, **kwargs)
        self._read_dialog_surface_color()

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
        self._read_dialog_surface_color()
        self.polish_themed()
        super().on_theme_changed()
        apply_geometry = getattr(self, "_apply_dialog_geometry", None)
        if callable(apply_geometry):
            defer_dialog_geometry(self, apply_geometry)
        self.on_dialog_theme_changed()

    def on_dialog_theme_changed(self) -> None:
        """Override for dialog-specific theme side effects after the UI exists."""

    def _read_dialog_surface_color(self) -> None:
        """Re-read the ``dialog.background`` token into ``_dialog_surface_color``.

        Top-level QDialog QSS surface paint dies with the app QSS: with no
        stylesheet the dialog paints the QPalette Window role, which hosts
        keep darker than the dialog surface token (dark Window ``#1e1e1e``
        vs ``dialog.background`` ``#2b2b2b``). Re-read on every theme change
        (never cached forever): hosts may override the token via
        ``ThemeManager.set_color``. ThemeManager may be uninitialized in
        some test contexts — fall back to the palette Window role as a last
        resort.
        """
        try:
            color = try_resolve_theme_color(self._theme_manager, "dialog.background")
        except Exception:
            color = None
        if color is None or not color.isValid():
            color = QColor(self.palette().window().color())
        self._dialog_surface_color = color

    def paintEvent(self, event) -> None:  # noqa: N802
        """Fill the dialog surface with the ``dialog.background`` token.

        Same explicit-paint pattern as the toolkit ``_SurfaceWidget`` /
        ``IconListWidget``: the dialog owns its surface instead of relying
        on application QSS ``QDialog#X`` rules.
        """
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._dialog_surface_color)
        painter.end()