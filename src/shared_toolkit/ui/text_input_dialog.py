"""Themed single-line text prompt — replacement for ``QInputDialog.getText``.

Uses the same CSD / rounded-mask path as :class:`AppMessageDialog` so
corner clipping stays correct under custom decorations.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QDialog, QGridLayout, QVBoxLayout, QWidget

from shared_toolkit.ui.themed_dialog import ThemedDialog
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import Button, CustomLineEdit, Label
from utils.resource_loader import resource_path

_PROMPT_PIXEL_SIZE = 14


class AppTextInputDialog(ThemedDialog):
    """Small themed text prompt with toolkit controls and explicit CSD."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        title: str = "",
        prompt: str = "",
        text: str = "",
        ok_text: str = "OK",
        cancel_text: str = "Cancel",
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._prompt = prompt
        self._initial_text = text
        self._ok_text = ok_text
        self._cancel_text = cancel_text
        self.theme_manager = ThemeManager.get_instance()
        # Own CSD explicitly — do not let the app-wide Polish interceptor
        # decorate first (avoids a second title bar / wrong chrome race).
        self._csd_opt_out = True

        self.setObjectName("AppTextInputDialog")
        self.setWindowIcon(QIcon(resource_path("resources/icons/icon.png")))
        self.setWindowTitle(title)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setSizeGripEnabled(False)

        self._build_ui()
        self._apply_geometry()

        from shared_toolkit.ui.decorate_dialog import decorate_dialog

        decorate_dialog(self, title=title, resizable=True)
        self.mark_theme_ui_ready()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 16)
        root.setSpacing(12)

        self._prompt_label = Label(
            self._prompt,
            variant="body",
            pixel_size=_PROMPT_PIXEL_SIZE,
            parent=self,
        )
        self._prompt_label.setWordWrap(True)
        root.addWidget(self._prompt_label)

        self._line_edit = CustomLineEdit(parent=self)
        self._line_edit.setText(self._initial_text)
        self._line_edit.selectAll()
        self._line_edit.returnPressed.connect(self.accept)
        root.addWidget(self._line_edit)

        actions = QWidget(self)
        action_layout = QGridLayout(actions)
        action_layout.setContentsMargins(0, 4, 0, 0)
        action_layout.setHorizontalSpacing(8)
        action_layout.setColumnStretch(0, 1)

        self._cancel_button = Button(
            text=self._cancel_text, variant="surface", parent=actions
        )
        self._cancel_button.setMinimumSize(96, 34)
        self._cancel_button.clicked.connect(self.reject)

        self._ok_button = Button(
            text=self._ok_text, variant="surface", parent=actions
        )
        self._ok_button.setMinimumSize(96, 34)
        self._ok_button.clicked.connect(self.accept)

        action_layout.addWidget(self._cancel_button, 0, 1)
        action_layout.addWidget(self._ok_button, 0, 2)
        root.addWidget(actions)

    def _apply_geometry(self) -> None:
        self.adjustSize()
        hint = self.sizeHint()
        width = max(360, min(480, hint.width() + 48))
        height = max(160, hint.height() + 16)
        self.setMinimumSize(width, height)
        self.resize(width, height)

    def text_value(self) -> str:
        return self._line_edit.text()

    def showEvent(self, event) -> None:  # noqa: N802 — Qt API
        super().showEvent(event)
        self._line_edit.setFocus(Qt.FocusReason.PopupFocusReason)
        self._line_edit.selectAll()

    @classmethod
    def get_text(
        cls,
        parent: QWidget | None,
        title: str,
        prompt: str,
        text: str = "",
        *,
        ok_text: str = "OK",
        cancel_text: str = "Cancel",
    ) -> tuple[str, bool]:
        dialog = cls(
            parent,
            title=title,
            prompt=prompt,
            text=text,
            ok_text=ok_text,
            cancel_text=cancel_text,
        )
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        value = dialog.text_value() if accepted else text
        return value, accepted
