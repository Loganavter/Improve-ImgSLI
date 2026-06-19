from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from sli_ui_toolkit.widgets import Button, CustomLineEdit


class DialogActionBar(QWidget):
    def __init__(
        self,
        primary_text: str,
        secondary_text: str,
        *,
        primary_min_size: tuple[int, int] = (100, 36),
        secondary_min_size: tuple[int, int] = (100, 36),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addStretch()

        self.secondary_button = Button(text=secondary_text, variant="surface", parent=self)
        self.secondary_button.setMinimumSize(*secondary_min_size)
        self.primary_button = Button(text=primary_text, variant="surface", parent=self)
        self.primary_button.setMinimumSize(*primary_min_size)

        layout.addWidget(self.secondary_button)
        layout.addWidget(self.primary_button)


class OutputPathSection(QWidget):
    def __init__(
        self,
        *,
        directory_label_text: str,
        browse_text: str,
        set_favorite_text: str,
        use_favorite_text: str,
        filename_label_text: str,
        on_browse: Callable[[], None] | None = None,
        on_set_favorite: Callable[[], None] | None = None,
        on_use_favorite: Callable[[], None] | None = None,
        use_custom_line_edit: bool = True,
        filename_editor_factory: type[QLineEdit] | Callable[[], QLineEdit] = CustomLineEdit,
        button_min_size: tuple[int, int] | None = None,
        button_fixed_height: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.dir_label = QLabel(directory_label_text, self)
        self.dir_picker_row = QWidget(self)
        dir_layout = QHBoxLayout(self.dir_picker_row)
        dir_layout.setContentsMargins(0, 0, 0, 0)
        dir_layout.setSpacing(6)

        self.edit_dir = CustomLineEdit(self) if use_custom_line_edit else QLineEdit(self)
        self.btn_browse_dir = Button(text=browse_text, variant="surface", parent=self)
        self.favorite_actions = QWidget(self)
        fav_layout = QHBoxLayout(self.favorite_actions)
        fav_layout.setContentsMargins(0, 0, 0, 0)
        fav_layout.setSpacing(6)
        self.btn_set_favorite = Button(text=set_favorite_text, variant="surface", parent=self)
        self.btn_use_favorite = Button(text=use_favorite_text, variant="surface", parent=self)

        for button in (self.btn_browse_dir, self.btn_set_favorite, self.btn_use_favorite):
            if button_min_size is not None:
                button.setMinimumSize(*button_min_size)
            if button_fixed_height is not None:
                button.setFixedHeight(button_fixed_height)

        if on_browse is not None:
            self.btn_browse_dir.clicked.connect(on_browse)
        if on_set_favorite is not None:
            self.btn_set_favorite.clicked.connect(on_set_favorite)
        if on_use_favorite is not None:
            self.btn_use_favorite.clicked.connect(on_use_favorite)

        fav_layout.addWidget(self.btn_set_favorite)
        fav_layout.addWidget(self.btn_use_favorite)

        dir_layout.addWidget(self.edit_dir, 1)
        dir_layout.addWidget(self.btn_browse_dir)

        self.filename_label = QLabel(filename_label_text, self)
        self.filename_edit = filename_editor_factory()

        layout.addWidget(self.dir_label)
        layout.addWidget(self.dir_picker_row)
        layout.addWidget(self.favorite_actions)
        layout.addWidget(self.filename_label)
        layout.addWidget(self.filename_edit)
