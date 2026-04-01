from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QWidget

from ..atomic.custom_button import CustomButton
from ..atomic.custom_line_edit import CustomLineEdit

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

        self.browse_button = CustomButton(None, browse_text)
        self.browse_button.setCursor(Qt.CursorShape.PointingHandCursor)
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

        self.btn_set_favorite = CustomButton(None, set_favorite_text)
        self.btn_use_favorite = CustomButton(None, use_favorite_text)
        for button in (self.btn_set_favorite, self.btn_use_favorite):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            if button_fixed_height is not None:
                button.setFixedHeight(button_fixed_height)

        if on_set_favorite is not None:
            self.btn_set_favorite.clicked.connect(on_set_favorite)
        if on_use_favorite is not None:
            self.btn_use_favorite.clicked.connect(on_use_favorite)

        layout.addWidget(self.btn_set_favorite)
        layout.addWidget(self.btn_use_favorite)
