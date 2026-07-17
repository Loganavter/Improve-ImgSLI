"""ThemedDialog repolishes and defers geometry once the UI is ready."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout

from shared_toolkit.ui.themed_dialog import ThemedDialog

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or _APP or QApplication([])
    return _APP


class _ProbeDialog(ThemedDialog):
    def __init__(self):
        super().__init__()
        self.polish_calls = 0
        self.geometry_calls = 0
        self.extra_calls = 0
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("probe", self))
        self.install_dialog_geometry(self._record_geometry)
        self.mark_theme_ui_ready()

    def polish_themed(self) -> None:
        self.polish_calls += 1

    def on_dialog_theme_changed(self) -> None:
        self.extra_calls += 1

    def _record_geometry(self) -> None:
        self.geometry_calls += 1


def test_themed_dialog_skips_theme_work_until_ui_ready():
    app = _app()
    dialog = ThemedDialog()
    dialog._theme_ui_ready = False
    dialog.on_theme_changed()
    assert dialog._theme_ui_ready is False

    dialog.deleteLater()
    app.processEvents()


def test_themed_dialog_repaints_and_defers_geometry_after_mark_ready():
    app = _app()
    dialog = _ProbeDialog()
    app.processEvents()

    assert dialog.polish_calls == 1
    assert dialog.geometry_calls >= 1
    assert dialog.extra_calls == 1

    dialog.on_theme_changed()
    app.processEvents()

    assert dialog.polish_calls == 2
    assert dialog.geometry_calls >= 2
    assert dialog.extra_calls == 2

    dialog.deleteLater()
    app.processEvents()
