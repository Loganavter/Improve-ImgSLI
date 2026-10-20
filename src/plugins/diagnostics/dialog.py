"""Consent / preview dialog for the diagnostics report.

Shows exactly what will be copied / saved / attached to an issue, with
``Copy`` / ``Save…`` / ``Open issue`` / ``Close`` actions. Built on the
toolkit painter pipeline (``ThemedDialog`` + toolkit ``Button`` / ``Text``) —
no QSS, no manual theming. The report itself is a read-only
``Text(mode="code")``; the host ``SurfaceScrollArea`` scrolls it (``Text``
never scrolls itself).
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, SurfaceScrollArea, Text

from resources.translations import get_current_language
from resources.translations import tr as app_tr
from shared_toolkit.ui.themed_dialog import ThemedDialog
from utils.resource_loader import resource_path

from .report import DiagnosticsReport

__all__ = ["DiagnosticsDialog", "show_diagnostics_dialog"]

_DIALOG_MIN_WIDTH = 780
_DIALOG_MIN_HEIGHT = 560


class DiagnosticsDialog(ThemedDialog):
    """Preview the diagnostics report and offer Copy / Save / Open issue."""

    def __init__(
        self,
        report: DiagnosticsReport,
        *,
        parent: Any = None,
        current_language: str | None = None,
        tr_func: Callable[..., str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.report = report
        self.current_language = current_language or get_current_language() or "en"
        # Never assign to self.tr — QObject.tr is Qt's; use _tr_func/_tr.
        self._tr_func = tr_func if callable(tr_func) else app_tr

        self.setObjectName("DiagnosticsDialog")
        self.setWindowIcon(QIcon(resource_path("resources/icons/icon.png")))
        self.setWindowTitle(self._tr("diagnostics.title", "Report a problem"))
        self.setSizeGripEnabled(True)

        self._init_ui()
        self.install_dialog_geometry(self._apply_dialog_geometry)
        self.mark_theme_ui_ready()

        from shared_toolkit.ui.decorate_dialog import (
            decorate_dialog,
            register_dialog_auto_navigation,
            register_dialog_title_bar_navigation,
        )

        decorate_dialog(self, title=self._tr("diagnostics.title", "Report a problem"))
        register_dialog_title_bar_navigation(self)
        # Report view above, action row below, in visual order.
        register_dialog_auto_navigation(
            self,
            [
                [self.preview],
                [
                    self.open_issue_button,
                    self.copy_button,
                    self.save_button,
                    self.close_button,
                ],
            ],
            tag="diagnostics",
        )
        QTimer.singleShot(0, self._finalize_layout_and_size)

    # -- i18n -------------------------------------------------------------

    def _tr(self, key: str, default: str) -> str:
        text = self._tr_func(key, self.current_language)
        return default if text == key else text

    # -- build ------------------------------------------------------------

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(scaled_px(14), scaled_px(14), scaled_px(14), scaled_px(14))
        root.setSpacing(scaled_px(10))

        self.summary_label = Text(
            self._tr("diagnostics.summary", ""), self, mode="plain"
        )
        self.summary_label.setWordWrap(True)
        root.addWidget(self.summary_label)

        self.no_screenshots_label = Text(
            self._tr("diagnostics.no_screenshots", ""), self, mode="plain"
        )
        self.no_screenshots_label.setWordWrap(True)
        root.addWidget(self.no_screenshots_label)

        self.preview_label = Text(
            self._tr("diagnostics.preview_label", ""), self, mode="plain"
        )
        root.addWidget(self.preview_label)

        self.preview = Text(self.report.text, mode="code")
        self.preview.setObjectName("diagnostics-report")
        # One keyboard stop for the whole report composite (the old
        # ``TextView`` was a focusable scroll area around this engine): the
        # row section needs a focus-capable control it can land on.
        self.preview.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Read-only painted buffer: the host scroll area owns scrolling and
        # the surface fill (old ``TextView`` was a QScrollArea wrapping the
        # same engine — the composition is now explicit).
        self.preview_scroll = SurfaceScrollArea(self)
        self.preview_scroll.setMinimumSize(0, 1)
        # Keyboard ownership stays with the report control declared in the
        # dialog's navigation row (the old ``TextView`` was both at once).
        self.preview_scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.preview_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.preview_scroll.setWidget(self.preview)
        root.addWidget(self.preview_scroll, 1)

        self._init_actions(root)

    def _init_actions(self, root: QVBoxLayout) -> None:
        actions = QWidget(self)
        layout = QGridLayout(actions)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(scaled_px(8))
        layout.setColumnStretch(0, 1)

        self.open_issue_button = Button(
            text=self._tr("diagnostics.open_issue", "Open issue"),
            variant="accent",
            parent=actions,
        )
        self.copy_button = Button(
            text=self._tr("diagnostics.copy", "Copy"),
            variant="surface",
            parent=actions,
        )
        self.save_button = Button(
            text=self._tr("diagnostics.save", "Save…"),
            variant="surface",
            parent=actions,
        )
        self.close_button = Button(
            text=self._tr("diagnostics.close", "Close"),
            variant="surface",
            parent=actions,
        )
        for button in (
            self.open_issue_button,
            self.copy_button,
            self.save_button,
            self.close_button,
        ):
            button.setMinimumSize(scaled_px(110), scaled_px(36))

        self.open_issue_button.clicked.connect(self._open_issue)
        self.copy_button.clicked.connect(self._copy)
        self.save_button.clicked.connect(self._save)
        self.close_button.clicked.connect(self.accept)

        layout.addWidget(self.open_issue_button, 0, 1)
        layout.addWidget(self.copy_button, 0, 2)
        layout.addWidget(self.save_button, 0, 3)
        layout.addWidget(self.close_button, 0, 4)
        root.addWidget(actions)

    # -- geometry ---------------------------------------------------------

    def _apply_dialog_geometry(self) -> None:
        try:
            self.setMinimumSize(scaled_px(_DIALOG_MIN_WIDTH), scaled_px(_DIALOG_MIN_HEIGHT))
            if self.width() < scaled_px(_DIALOG_MIN_WIDTH) or self.height() < scaled_px(_DIALOG_MIN_HEIGHT):
                self.resize(scaled_px(_DIALOG_MIN_WIDTH), scaled_px(_DIALOG_MIN_HEIGHT))
        except Exception:
            pass

    def _finalize_layout_and_size(self) -> None:
        self._apply_dialog_geometry()
        try:
            from sli_ui_toolkit.ui.windows.csd_helpers import sync_csd_chrome

            sync_csd_chrome(self)
        except Exception:
            pass

    def showEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().showEvent(event)
        self._finalize_layout_and_size()

    # -- actions ----------------------------------------------------------

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.report.text)

    def _save(self) -> None:
        path, _selected = QFileDialog.getSaveFileName(
            self,
            self._tr("diagnostics.save_dialog_title", "Save diagnostics report"),
            "imgsli-diagnostics-report.txt",
            "Text (*.txt)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(self.report.text)
        except OSError:
            return

    def _open_issue(self) -> None:
        try:
            QDesktopServices.openUrl(QUrl(self.report.issue_url()))
        except Exception:
            pass


def show_diagnostics_dialog(
    report: DiagnosticsReport,
    *,
    parent: Any = None,
    current_language: str | None = None,
    tr_func: Callable[..., str] | None = None,
) -> DiagnosticsDialog:
    dialog = DiagnosticsDialog(
        report,
        parent=parent,
        current_language=current_language,
        tr_func=tr_func,
    )
    dialog.show()
    dialog.raise_()
    # Explicit user-foreground flow, but never kick an already-active window
    # (Wayland busy-cursor flash — see contracts/test_no_unconditional_activation).
    if not dialog.isActiveWindow():
        dialog.activateWindow()
    return dialog
