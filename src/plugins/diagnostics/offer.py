"""The startup offer: "the previous session ended abnormally — send a report?".

One small dialog, not a decision the app makes for the user: nothing is collected
until the button is pressed, and the report itself still has Copy / Save / Open
issue (``dialog.py``). Three answers:

* **Create report** — build it now (it carries the previous log tail and, when a
  fault dump exists, its traceback) and open the report dialog;
* **Not now** — dismiss; the next start offers again;
* **Don't ask again** — persist the opt-out (``diagnostics/offer_unclean_report``).

Built from the toolkit widgets the diagnostics dialog already uses, so it follows
theme/scale like every other dialog.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, Text
from shared_toolkit.ui.themed_dialog import ThemedDialog
from resources.translations import get_current_language

#: Minimum size of the offer (smaller than the report dialog: it is a question,
#: not a document preview).
_DIALOG_MIN_WIDTH = 520
_DIALOG_MIN_HEIGHT = 240


#: The app translator, imported lazily so this module stays importable in a test.
def _default_tr(key: str, language: str | None = None) -> str:
    try:
        from plugins.diagnostics.dialog import app_tr

        return app_tr(key, language)
    except Exception:
        return key


class UncleanShutdownDialog(ThemedDialog):
    """Offer a diagnostics report for a session that did not exit normally."""

    def __init__(
        self,
        summary: str,
        *,
        parent: Any = None,
        language: str | None = None,
        tr_func: Callable[..., str] | None = None,
        on_report: Callable[[], None] | None = None,
        on_suppress: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.summary = summary
        self.language = language or get_current_language() or "en"
        self._tr_func = tr_func if callable(tr_func) else _default_tr
        self._on_report = on_report
        self._on_suppress = on_suppress

        self.setObjectName("UncleanShutdownDialog")
        self.setWindowTitle(self._tr("diagnostics.unclean_title", "Previous session"))
        self._init_ui()
        self.install_dialog_geometry(self._apply_dialog_geometry)
        self.mark_theme_ui_ready()

        try:
            from shared_toolkit.ui.decorate_dialog import (
                decorate_dialog,
                register_dialog_auto_navigation,
            )

            decorate_dialog(self, title=self._tr("diagnostics.unclean_title", "Previous session"))
            register_dialog_auto_navigation(
                self,
                [[self.report_button], [self.dismiss_button, self.never_button]],
                tag="unclean-shutdown",
            )
        except Exception:
            pass
        QTimer.singleShot(0, self._finalize_layout_and_size)

    # -- geometry ---------------------------------------------------------

    def _apply_dialog_geometry(self) -> None:
        try:
            self.setMinimumSize(
                scaled_px(_DIALOG_MIN_WIDTH), scaled_px(_DIALOG_MIN_HEIGHT)
            )
            if (
                self.width() < scaled_px(_DIALOG_MIN_WIDTH)
                or self.height() < scaled_px(_DIALOG_MIN_HEIGHT)
            ):
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

    # -- i18n -------------------------------------------------------------

    def _tr(self, key: str, default: str) -> str:
        try:
            text = self._tr_func(key, self.language)
        except Exception:
            text = key
        return default if not text or text == key else text

    # -- build ------------------------------------------------------------

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(
            scaled_px(14), scaled_px(14), scaled_px(14), scaled_px(14)
        )
        root.setSpacing(scaled_px(10))

        self.body = Text(self._tr("diagnostics.unclean_body", ""), self, mode="plain")
        self.body.setWordWrap(True)
        root.addWidget(self.body)

        # What the report WOULD carry, said before anything is collected.
        self.detail = Text(self.summary, self, mode="plain")
        self.detail.setWordWrap(True)
        root.addWidget(self.detail)

        row = QHBoxLayout()
        row.addStretch(1)
        self.never_button = Button(
            text=self._tr("diagnostics.unclean_never", "Don't ask again"),
            variant="ghost",
            parent=self,
        )
        self.dismiss_button = Button(
            text=self._tr("diagnostics.unclean_dismiss", "Not now"),
            variant="ghost",
            parent=self,
        )
        self.report_button = Button(
            text=self._tr("diagnostics.unclean_create", "Create report"),
            variant="primary",
            parent=self,
        )
        for button in (self.never_button, self.dismiss_button, self.report_button):
            row.addWidget(button)
        root.addLayout(row)

        self.dismiss_button.clicked.connect(self.close)
        self.never_button.clicked.connect(self._on_never)
        self.report_button.clicked.connect(self._on_report_clicked)

    # -- actions ----------------------------------------------------------

    def _on_never(self) -> None:
        if self._on_suppress is not None:
            try:
                self._on_suppress()
            except Exception:
                pass
        self.close()

    def _on_report_clicked(self) -> None:
        self.close()
        if self._on_report is not None:
            try:
                self._on_report()
            except Exception:
                pass


def show_unclean_shutdown_dialog(
    summary: str,
    *,
    parent: Any = None,
    on_report: Callable[[], None] | None = None,
    on_suppress: Callable[[], None] | None = None,
    window_icon: str | None = None,
) -> UncleanShutdownDialog:
    """Create, decorate and show the offer; returns the dialog (non-modal)."""
    dialog = UncleanShutdownDialog(
        summary, parent=parent, on_report=on_report, on_suppress=on_suppress
    )
    try:
        if window_icon:
            dialog.setWindowIcon(QIcon(window_icon))
    except Exception:
        pass
    dialog.show()
    return dialog


__all__ = ["UncleanShutdownDialog", "show_unclean_shutdown_dialog"]
