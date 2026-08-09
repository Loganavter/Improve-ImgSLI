"""ColorSwatch — round Button that opens a themed ColorPickerDialog on click.

App-level composite. Lives here (not in sli_ui_toolkit) because picker
integration is a product concern, not a generic widget primitive.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import Button

from ui.theming import resolve_theme_color
from ui.widgets.color_picker_dialog import ColorPickerDialog


class ColorSwatch(Button):
    colorChanged = Signal(QColor)

    def __init__(
        self,
        color: QColor | None = None,
        *,
        size: int = 28,
        alpha: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        initial = QColor(color) if color is not None else QColor(255, 255, 255)
        tm = ThemeManager.get_instance()
        super().__init__(
            size=(size, size),
            corner_radius=max(0, size // 2),
            parent=parent,
        )
        self._color = initial
        # Exact chip color as base; hover overlays remain enabled (bg unlocked).
        self.set_override_bg_color(initial)
        self._dialog: ColorPickerDialog | None = None
        self._alpha = bool(alpha)
        self.clicked.connect(self._open_dialog)
        tm.theme_changed.connect(self._refresh_border)
        self._refresh_border()

    def _refresh_border(self) -> None:
        # Use a contrast token (foreground text color) instead of the very pale
        # dialog.border — the swatch sits on flyout.background which is close to
        # dialog.border, leaving the border invisible.
        tm = ThemeManager.get_instance()
        try:
            border = QColor(resolve_theme_color(tm, "list_item.text.normal"))
        except Exception:
            border = QColor("#888888")
        self.setBorderColor(border)

    def color(self) -> QColor:
        return QColor(self._color)

    def set_color(self, color: QColor) -> None:
        if not color.isValid():
            return
        self._color = QColor(color)
        self.set_override_bg_color(QColor(color))

    setColor = set_color

    def _open_dialog(self) -> None:
        if self._dialog is not None and self._dialog.isVisible():
            self._dialog.raise_()
            self._dialog.activateWindow()
            return
        parent_window = self.window()
        dialog = ColorPickerDialog(self._color, parent_window, show_alpha=self._alpha)
        dialog.setModal(False)

        def on_selected(c: QColor) -> None:
            if c.isValid():
                self.set_color(c)
                self.colorChanged.emit(QColor(c))

        def on_finished(_result: int) -> None:
            self._dialog = None
            self.clearFocus()

        dialog.colorSelected.connect(on_selected)
        dialog.finished.connect(on_finished)
        self._dialog = dialog
        dialog.show()
