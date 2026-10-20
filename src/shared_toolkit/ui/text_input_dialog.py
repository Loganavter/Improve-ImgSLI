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
from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, CustomLineEdit, Text
from utils.resource_loader import resource_path

_PROMPT_PIXEL_SIZE = 14

#: Design px of the prompt's root chrome, resolved through ``scaled_px`` at
#: use time and re-resolved on a live ``UiScale`` change.
_ROOT_MARGIN = (18, 14, 18, 16)  # left, top, right, bottom
_ROOT_SPACING_PX = 12
_ACTIONS_TOP_MARGIN_PX = 4


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
        self._connect_design_metrics()

        from shared_toolkit.ui.decorate_dialog import decorate_dialog

        decorate_dialog(self, title=title, resizable=True)
        self.mark_theme_ui_ready()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        self._apply_root_design_metrics(root)

        self._prompt_label = Text(
            self._prompt,
            mode="plain",
            variant="body",
            pixel_size=_PROMPT_PIXEL_SIZE,
            parent=self,
        )
        self._prompt_label.setWordWrap(True)
        root.addWidget(self._prompt_label)

        self._line_edit = CustomLineEdit(parent=self)
        self._line_edit.setObjectName("text-input-field")
        self._line_edit.setText(self._initial_text)
        self._line_edit.selectAll()
        self._line_edit.returnPressed.connect(self.accept)
        root.addWidget(self._line_edit)

        actions = QWidget(self)
        action_layout = QGridLayout(actions)
        action_layout.setContentsMargins(
            0, scaled_px(_ACTIONS_TOP_MARGIN_PX), 0, 0
        )
        action_layout.setHorizontalSpacing(8)
        action_layout.setColumnStretch(0, 1)

        self._cancel_button = Button(
            text=self._cancel_text, variant="surface", parent=actions
        )
        self._cancel_button.setObjectName("text-input-cancel")
        self._cancel_button.setMinimumSize(scaled_px(96), scaled_px(34))
        self._cancel_button.clicked.connect(self.reject)

        self._ok_button = Button(
            text=self._ok_text, variant="surface", parent=actions
        )
        self._ok_button.setObjectName("text-input-ok")
        self._ok_button.setMinimumSize(scaled_px(96), scaled_px(34))
        self._ok_button.clicked.connect(self.accept)

        action_layout.addWidget(self._cancel_button, 0, 1)
        action_layout.addWidget(self._ok_button, 0, 2)
        root.addWidget(actions)

    @staticmethod
    def _apply_root_design_metrics(root: QVBoxLayout) -> None:
        """Resolve the root layout's design px at use time (not at import)."""
        root.setContentsMargins(*(scaled_px(v) for v in _ROOT_MARGIN))
        root.setSpacing(scaled_px(_ROOT_SPACING_PX))

    def _connect_design_metrics(self) -> None:
        """Re-resolve the root chrome when the UI scale changes live."""
        from sli_ui_toolkit.ui.managers import connect_ui_metrics
        from sli_ui_toolkit.ui.managers.ui_metrics import AXIS_SCALE

        connect_ui_metrics(
            self, self._on_design_metrics_changed, axes=frozenset({AXIS_SCALE})
        )

    def _on_design_metrics_changed(self, *_args) -> None:
        root = self.layout()
        if root is not None:
            self._apply_root_design_metrics(root)
        self.updateGeometry()

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
