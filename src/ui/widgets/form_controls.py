from __future__ import annotations

from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

from collections.abc import Callable

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from sli_ui_toolkit.widgets import DEFER_CLICK_AWAIT_RIPPLE, Button, CustomLineEdit, Label
from sli_ui_toolkit.managers import UiScale, scaled_px


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
        # Fixed vertically so height squeeze collapses stretch above, not OK/Cancel.
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(scaled_px(8))
        layout.addStretch()

        self._primary_min_size = primary_min_size
        self._secondary_min_size = secondary_min_size

        # Create with real text (like settings) so toolkit Button takes the
        # text-geometry path — empty→setText clears minimumWidth and lets
        # buttons collapse to ~36px.
        self.secondary_button = Button(
            text=secondary_text, variant="surface", parent=self
        )
        self.primary_button = Button(
            text=primary_text, variant="surface", parent=self
        )
        self._apply_button_minimums()

        layout.addWidget(self.secondary_button)
        layout.addWidget(self.primary_button)
        self.lock_content_minimum_height()
        UiScale.get_instance().scale_changed.connect(self._on_scale_changed)

    def _on_scale_changed(self, _factor: float) -> None:
        self._apply_button_minimums()
        # The lock is grow-only; drop it first so a shrink back to a smaller
        # factor is not stuck at the larger minimum.
        self.setMinimumHeight(0)
        self.setMaximumHeight(16777215)
        self.lock_content_minimum_height()
        self.updateGeometry()
        self.update()

    def _apply_button_minimums(self) -> None:
        self.secondary_button.setMinimumSize(
            *(scaled_px(v) for v in self._secondary_min_size)
        )
        self.primary_button.setMinimumSize(*(scaled_px(v) for v in self._primary_min_size))
        for button in (self.secondary_button, self.primary_button):
            button.setSizePolicy(
                QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
            )

    def lock_content_minimum_height(self) -> None:
        """Pin bar height to the taller of configured mins and sizeHint."""
        self.ensurePolished()
        hint_h = max(
            self.sizeHint().height(),
            scaled_px(self._primary_min_size[1]),
            scaled_px(self._secondary_min_size[1]),
        )
        if hint_h > 0:
            self.setMinimumHeight(max(self.minimumHeight(), hint_h))
            self.setMaximumHeight(max(self.minimumHeight(), hint_h))

    def set_button_texts(self, primary_text: str, secondary_text: str) -> None:
        self.primary_button.setText(primary_text)
        self.secondary_button.setText(secondary_text)
        self._apply_button_minimums()
        self.lock_content_minimum_height()


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
        # Prefer horizontal flex; never shrink below content height — Preferred
        # vertical would crush Browse / favorite buttons when the dialog is
        # height-compressed (CSD startSystemResize often ignores Qt mins).
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(scaled_px(6))

        self.dir_label = Label(directory_label_text, self)
        self.dir_picker_row = QWidget(self)
        self.dir_picker_row.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        dir_layout = QHBoxLayout(self.dir_picker_row)
        dir_layout.setContentsMargins(0, 0, 0, 0)
        dir_layout.setSpacing(scaled_px(6))

        self.edit_dir = CustomLineEdit(self) if use_custom_line_edit else QLineEdit(self)
        self.btn_browse_dir = Button(
            text=browse_text,
            variant="surface",
            parent=self,
            # on_browse (both Export and Video Editor dialogs) opens a
            # modal QFileDialog -- ripple must finish first.
            defer_click=DEFER_CLICK_AWAIT_RIPPLE,
        )
        self.favorite_actions = QWidget(self)
        self.favorite_actions.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        fav_layout = QHBoxLayout(self.favorite_actions)
        fav_layout.setContentsMargins(0, 0, 0, 0)
        fav_layout.setSpacing(scaled_px(6))
        self.btn_set_favorite = Button(text=set_favorite_text, variant="surface", parent=self)
        self.btn_use_favorite = Button(text=use_favorite_text, variant="surface", parent=self)

        # Design px; re-applied scaled on ``scale_changed`` so live factor
        # changes resize the output-path buttons (toolkit Button only
        # re-applies its own ``size=`` design size, not external min/fixed).
        self._design_button_min_size = button_min_size
        self._design_button_fixed_height = button_fixed_height
        self._apply_button_sizes()
        UiScale.get_instance().scale_changed.connect(self._on_scale_changed)

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

        self.filename_label = Label(filename_label_text, self)
        self.filename_edit = filename_editor_factory()

        layout.addWidget(self.dir_label)
        layout.addWidget(self.dir_picker_row)
        layout.addWidget(self.favorite_actions)
        layout.addWidget(self.filename_label)
        layout.addWidget(self.filename_edit)

    def _apply_button_sizes(self) -> None:
        for button in (self.btn_browse_dir, self.btn_set_favorite, self.btn_use_favorite):
            if self._design_button_min_size is not None:
                button.setMinimumSize(
                    *(scaled_px(v) for v in self._design_button_min_size)
                )
            if self._design_button_fixed_height is not None:
                button.setFixedHeight(scaled_px(self._design_button_fixed_height))

    def _on_scale_changed(self, _factor: float) -> None:
        self._apply_button_sizes()
        self.updateGeometry()
        self.update()

    def lock_content_minimum_height(self) -> None:
        """Pin vertical minimum to the current content sizeHint."""
        self.ensurePolished()
        self.adjustSize()
        hint_h = self.sizeHint().height()
        if hint_h > 0:
            self.setMinimumHeight(max(self.minimumHeight(), hint_h))

    def apply_to(self, dialog: QWidget) -> None:
        """Wire sub-widgets onto ``dialog`` for backward compatibility.

        Sets ``dialog.output_section`` and aliases each sub-widget so
        existing dialog code that reads ``dialog.edit_dir`` etc. keeps
        working without per-site boilerplate.
        """
        dialog.output_section = self
        dialog.dir_picker_row = self.dir_picker_row
        dialog.edit_dir = self.edit_dir
        dialog.btn_browse_dir = self.btn_browse_dir
        dialog.favorite_actions = self.favorite_actions
        dialog.btn_set_favorite = self.btn_set_favorite
        dialog.btn_use_favorite = self.btn_use_favorite
        dialog.name_label = self.filename_label
        dialog.edit_name = self.filename_edit
        self.lock_content_minimum_height()


DialogActionBar.inspect_spec = InspectSpec(
    family="DialogActionBar",
    docs="docs/dev/widgets/form_controls.md",
)

OutputPathSection.inspect_spec = InspectSpec(
    family="OutputPathSection",
    state=(
        SpecField("directory", lambda w: w.edit_dir.text()),
        SpecField("filename", lambda w: w.filename_edit.text()),
    ),
    docs="docs/dev/widgets/form_controls.md",
)