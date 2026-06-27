"""Root widget for the image_compare tab.

Stage 2 of the migration: the widget now owns the assembled layout
tree (selection bar, checkbox bar, image container, footer, edit/save
rows). Primitive widgets (buttons, sliders, canvas) are still owned by
``MainWindowUI`` and exposed through the legacy ``ui.*`` attributes —
Stage 3 will route them via proxy properties.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from tabs.contract import TabContext
from tabs.image_compare.ui.layout import ImageCompareLayoutBuilder


class ImageCompareWidget(QWidget):
    def __init__(
        self,
        parent: QWidget | None = None,
        context: TabContext | None = None,
        ui=None,
    ):
        super().__init__(parent)
        self._context = context
        self._ui = ui
        if ui is not None:
            ImageCompareLayoutBuilder(ui).build_into(self)
