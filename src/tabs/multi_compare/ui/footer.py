"""Footer bar for multi-compare tab."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget
from sli_ui_toolkit.i18n import translatable_text, translatable_tooltip
from sli_ui_toolkit.widgets import Button

from sli_ui_toolkit.i18n import tr
from ui.icon_manager import AppIcon


def _save_result_tr(_key: str, lang: str) -> str:
    result = tr("save_result", lang)
    return result if result != "save_result" else "Save result"


def _save_tooltip_tr(_key: str, lang: str) -> str:
    result = tr("tooltip.multi_compare_save_grid", lang)
    return (
        result
        if result != "tooltip.multi_compare_save_grid"
        else "Export the composed comparison grid"
    )


class MultiCompareFooter(QWidget):
    """Bottom bar: save composed grid (mirrors main workspace btn_save)."""

    save_clicked = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(44)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        text = _save_result_tr("save_result", "en")
        self.btn_save = Button(AppIcon.SAVE, text=text, variant="surface", parent=self)
        translatable_text(self.btn_save, "save_result", tr_func=_save_result_tr)
        translatable_tooltip(
            self.btn_save,
            "tooltip.multi_compare_save_grid",
            tr_func=_save_tooltip_tr,
        )
        self.btn_save.setMinimumHeight(32)
        self.btn_save.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.btn_save.clicked.connect(self.save_clicked)

        layout.addWidget(self.btn_save, 1)
