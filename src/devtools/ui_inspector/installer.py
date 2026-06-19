from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget

from devtools.ui_inspector.controller import UiInspectorController


def install_ui_inspector(app: QApplication, window: QWidget, theme_manager) -> None:
    if getattr(window, "_ui_inspector_controller", None) is not None:
        return
    qss_path = Path(__file__).resolve().parent / "resources" / "ui_inspector.qss"
    theme_manager.register_qss_path(str(qss_path))
    theme_manager.apply_theme_to_app(app)
    window._ui_inspector_controller = UiInspectorController(
        app,
        window,
        theme_manager,
    )
