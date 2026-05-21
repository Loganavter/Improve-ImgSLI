from __future__ import annotations

from typing import Callable

from PyQt6.QtWidgets import QHBoxLayout, QWidget

from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.atomic.custom_line_edit import CustomLineEdit
from sli_ui_toolkit.ui.widgets.helpers import apply_editable_text_behavior

class DirectoryPickerRow(QWidget):
    def __init__(
        self,
        browse_text: str,
        on_browse: Callable[[], None] | None = None,
        *,
        use_custom_line_edit: bool = True,
        button_min_size: tuple[int, int] | None = None,
        button_fixed_height: int | None = None,
        parent=None,
    ):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.line_edit = CustomLineEdit() if use_custom_line_edit else None
        if self.line_edit is None:
            from PyQt6.QtWidgets import QLineEdit

            self.line_edit = QLineEdit()
            apply_editable_text_behavior(self.line_edit)

        self.browse_button = Button(text=browse_text, variant="surface")
        if button_min_size is not None:
            self.browse_button.setMinimumSize(*button_min_size)
        if button_fixed_height is not None:
            self.browse_button.setFixedHeight(button_fixed_height)
        if on_browse is not None:
            self.browse_button.clicked.connect(on_browse)

        layout.addWidget(self.line_edit, 1)
        layout.addWidget(self.browse_button)

class FavoritePathActions(QWidget):
    def __init__(
        self,
        set_favorite_text: str,
        use_favorite_text: str,
        on_set_favorite: Callable[[], None] | None = None,
        on_use_favorite: Callable[[], None] | None = None,
        *,
        button_fixed_height: int | None = None,
        parent=None,
    ):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.btn_set_favorite = Button(text=set_favorite_text, variant="surface")
        self.btn_use_favorite = Button(text=use_favorite_text, variant="surface")
        for button in (self.btn_set_favorite, self.btn_use_favorite):
            if button_fixed_height is not None:
                button.setFixedHeight(button_fixed_height)

        if on_set_favorite is not None:
            self.btn_set_favorite.clicked.connect(on_set_favorite)
        if on_use_favorite is not None:
            self.btn_use_favorite.clicked.connect(on_use_favorite)

        layout.addWidget(self.btn_set_favorite)
        layout.addWidget(self.btn_use_favorite)
