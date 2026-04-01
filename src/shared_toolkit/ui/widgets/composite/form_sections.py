from __future__ import annotations

from typing import Callable

from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .path_controls import DirectoryPickerRow, FavoritePathActions

class OutputPathSection(QWidget):
    def __init__(
        self,
        *,
        browse_text: str,
        set_favorite_text: str,
        use_favorite_text: str,
        filename_label_text: str,
        directory_label_text: str | None = None,
        on_browse=None,
        on_set_favorite=None,
        on_use_favorite=None,
        use_custom_line_edit: bool = True,
        filename_editor_factory: Callable[[], QWidget] | None = None,
        button_min_size: tuple[int, int] | None = None,
        button_fixed_height: int | None = None,
        parent=None,
    ):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.directory_label = None
        if directory_label_text:
            self.directory_label = QLabel(directory_label_text)
            layout.addWidget(self.directory_label)

        self.dir_picker_row = DirectoryPickerRow(
            browse_text,
            on_browse,
            use_custom_line_edit=use_custom_line_edit,
            button_min_size=button_min_size,
            button_fixed_height=button_fixed_height,
        )
        self.edit_dir = self.dir_picker_row.line_edit
        self.btn_browse_dir = self.dir_picker_row.browse_button
        layout.addWidget(self.dir_picker_row)

        self.favorite_actions = FavoritePathActions(
            set_favorite_text,
            use_favorite_text,
            on_set_favorite,
            on_use_favorite,
            button_fixed_height=button_fixed_height,
        )
        self.btn_set_favorite = self.favorite_actions.btn_set_favorite
        self.btn_use_favorite = self.favorite_actions.btn_use_favorite
        layout.addWidget(self.favorite_actions)

        self.filename_label = QLabel(filename_label_text)
        layout.addWidget(self.filename_label)

        if filename_editor_factory is None:
            from PyQt6.QtWidgets import QLineEdit

            filename_editor_factory = QLineEdit

        self.filename_edit = filename_editor_factory()
        layout.addWidget(self.filename_edit)
