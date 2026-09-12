"""First-party modal alerts — replacement for ``QMessageBox`` in app code.

Owns layout, theming, and CSD explicitly instead of monkey-patching Qt's
``QMessageBox`` paint path.
"""

from __future__ import annotations

from enum import Enum, auto

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFont, QIcon, QPainter
from PySide6.QtWidgets import QDialog, QGridLayout, QVBoxLayout, QWidget

from shared_toolkit.ui.themed_dialog import ThemedDialog
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import Button, CheckBox, Label
from ui.theming import resolve_theme_color
from utils.resource_loader import resource_path


class MessageKind(Enum):
    INFORMATION = auto()
    WARNING = auto()
    CRITICAL = auto()
    QUESTION = auto()


_KIND_GLYPH: dict[MessageKind, str] = {
    MessageKind.INFORMATION: "i",
    MessageKind.WARNING: "!",
    MessageKind.CRITICAL: "×",
    MessageKind.QUESTION: "?",
}

_KIND_COLOR_TOKEN: dict[MessageKind, str] = {
    MessageKind.INFORMATION: "accent",
    MessageKind.WARNING: "accent",
    MessageKind.CRITICAL: "BrightText",
    MessageKind.QUESTION: "accent",
}

_BADGE_DIAMETER = 36
_BADGE_GLYPH_PIXEL_SIZE = 18
_MESSAGE_PIXEL_SIZE = 14


class _MessageKindBadge(QWidget):
    """Colored circle with a white severity glyph."""

    def __init__(
        self,
        kind: MessageKind,
        theme_manager: ThemeManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._kind = kind
        self._theme_manager = theme_manager
        self.setFixedSize(_BADGE_DIAMETER, _BADGE_DIAMETER)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def paintEvent(self, event) -> None:  # noqa: ARG002 — Qt API
        bg = QColor(resolve_theme_color(self._theme_manager, _KIND_COLOR_TOKEN[self._kind]))
        fg = QColor("#ffffff")
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg)
            radius = min(self.width(), self.height()) / 2.0
            painter.drawEllipse(
                (self.width() - 2 * radius) / 2.0,
                (self.height() - 2 * radius) / 2.0,
                2 * radius,
                2 * radius,
            )
            font = QFont(self.font())
            font.setPixelSize(_BADGE_GLYPH_PIXEL_SIZE)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(fg)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, _KIND_GLYPH[self._kind])
        finally:
            painter.end()

    def sizeHint(self) -> QSize:
        return QSize(_BADGE_DIAMETER, _BADGE_DIAMETER)


class AppMessageDialog(ThemedDialog):
    """Small themed alert with toolkit controls and explicit CSD."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        kind: MessageKind = MessageKind.INFORMATION,
        title: str = "",
        text: str = "",
        ok_text: str = "OK",
        checkbox_text: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._kind = kind
        self._title = title
        self._body_text = text
        self._ok_text = ok_text
        self._checkbox_text = checkbox_text
        self._dont_show_again = False
        self.theme_manager = ThemeManager.get_instance()
        # Own CSD explicitly — do not let the app-wide Polish interceptor
        # decorate first (avoids a second title bar / wrong chrome race).
        self._csd_opt_out = True

        self.setObjectName("AppMessageDialog")
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

    @property
    def dont_show_again(self) -> bool:
        """True when an optional checkbox was shown and checked on accept."""
        return bool(self._dont_show_again)

    def on_dialog_theme_changed(self) -> None:
        if getattr(self, "_kind_badge", None) is not None:
            self._kind_badge.update()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 16)
        root.setSpacing(14)

        body_row = QWidget(self)
        body_layout = QGridLayout(body_row)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setHorizontalSpacing(14)
        body_layout.setColumnStretch(1, 1)

        self._kind_badge = _MessageKindBadge(self._kind, self.theme_manager, body_row)

        self._message_label = Label(
            self._body_text,
            variant="body",
            pixel_size=_MESSAGE_PIXEL_SIZE,
            parent=body_row,
        )
        self._message_label.setWordWrap(True)
        self._message_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        body_layout.addWidget(self._kind_badge, 0, 0, Qt.AlignmentFlag.AlignTop)
        body_layout.addWidget(self._message_label, 0, 1)
        root.addWidget(body_row, 1)

        self._checkbox = None
        if self._checkbox_text:
            self._checkbox = CheckBox(self._checkbox_text, parent=self)
            self._checkbox.setChecked(False)
            root.addWidget(self._checkbox)

        actions = QWidget(self)
        action_layout = QGridLayout(actions)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setColumnStretch(0, 1)

        self._ok_button = Button(text=self._ok_text, variant="surface", parent=actions)
        self._ok_button.setMinimumSize(96, 34)
        self._ok_button.clicked.connect(self.accept)

        action_layout.addWidget(self._ok_button, 0, 1)
        root.addWidget(actions)

    def accept(self) -> None:
        if self._checkbox is not None:
            self._dont_show_again = bool(self._checkbox.isChecked())
        else:
            self._dont_show_again = False
        super().accept()

    def _apply_geometry(self) -> None:
        self.adjustSize()
        hint = self.sizeHint()
        width = max(340, min(540, hint.width() + 32))
        height = max(150, hint.height() + 16)
        self.setMinimumSize(width, height)
        self.resize(width, height)

    @classmethod
    def show_modal(
        cls,
        parent: QWidget | None,
        kind: MessageKind,
        title: str,
        text: str,
        *,
        ok_text: str = "OK",
        checkbox_text: str | None = None,
    ) -> QDialog.DialogCode:
        dialog = cls(
            parent,
            kind=kind,
            title=title,
            text=text,
            ok_text=ok_text,
            checkbox_text=checkbox_text,
        )
        return QDialog.DialogCode(dialog.exec())

    @classmethod
    def show_modal_ex(
        cls,
        parent: QWidget | None,
        kind: MessageKind,
        title: str,
        text: str,
        *,
        ok_text: str = "OK",
        checkbox_text: str | None = None,
    ) -> tuple[QDialog.DialogCode, bool]:
        """Like ``show_modal``, also returning the optional checkbox state."""
        dialog = cls(
            parent,
            kind=kind,
            title=title,
            text=text,
            ok_text=ok_text,
            checkbox_text=checkbox_text,
        )
        code = QDialog.DialogCode(dialog.exec())
        checked = bool(dialog.dont_show_again) if int(code) == int(
            QDialog.DialogCode.Accepted
        ) else False
        return code, checked

    @classmethod
    def information(
        cls,
        parent: QWidget | None,
        title: str,
        text: str,
        *,
        ok_text: str = "OK",
        checkbox_text: str | None = None,
    ) -> QDialog.DialogCode:
        return cls.show_modal(
            parent,
            MessageKind.INFORMATION,
            title,
            text,
            ok_text=ok_text,
            checkbox_text=checkbox_text,
        )

    @classmethod
    def warning(
        cls,
        parent: QWidget | None,
        title: str,
        text: str,
        *,
        ok_text: str = "OK",
        checkbox_text: str | None = None,
    ) -> QDialog.DialogCode:
        return cls.show_modal(
            parent,
            MessageKind.WARNING,
            title,
            text,
            ok_text=ok_text,
            checkbox_text=checkbox_text,
        )

    @classmethod
    def critical(
        cls,
        parent: QWidget | None,
        title: str,
        text: str,
        *,
        ok_text: str = "OK",
        checkbox_text: str | None = None,
    ) -> QDialog.DialogCode:
        return cls.show_modal(
            parent,
            MessageKind.CRITICAL,
            title,
            text,
            ok_text=ok_text,
            checkbox_text=checkbox_text,
        )


def open_non_modal_message(
    parent: QWidget | None,
    *,
    kind: MessageKind,
    title: str,
    text: str,
    ok_text: str = "OK",
) -> AppMessageDialog:
    """Show a non-blocking alert; caller may track lifetime if needed."""
    dialog = AppMessageDialog(
        parent,
        kind=kind,
        title=title,
        text=text,
        ok_text=ok_text,
    )
    dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.Window)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.setModal(False)
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    return dialog
