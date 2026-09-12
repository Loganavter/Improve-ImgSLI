from __future__ import annotations

import logging

from PySide6.QtWidgets import QApplication, QWidget

from devtools.ui_inspector.app_controller import AppInspectorController
from devtools.ui_inspector.app_window import AppInspectorWindow


class _ToolkitLogBridge(logging.Handler):
    """Forward ``sli_ui_toolkit.inspector`` records into the
    ``ImproveImgSLI`` pipeline so the inspector's own diagnostics
    (``[inspector-preview]`` lines) reach the app's log file — the app
    configures handlers only on the ``ImproveImgSLI`` logger, so toolkit
    records would otherwise die at the root logger."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            logging.getLogger("ImproveImgSLI").handle(record)
        except Exception:
            pass


def install_ui_inspector(app: QApplication, window: QWidget, theme_manager) -> None:
    """Wire the toolkit-based inspector (window + controller) into the app."""
    if getattr(window, "_ui_inspector_controller", None) is not None:
        return
    toolkit_logger = logging.getLogger("sli_ui_toolkit.inspector")
    toolkit_logger.addHandler(_ToolkitLogBridge())
    toolkit_logger.setLevel(logging.DEBUG)
    toolkit_logger.propagate = False
    inspector_window = AppInspectorWindow()
    controller = AppInspectorController(app, inspector_window, theme_manager)
    window._ui_inspector_controller = controller  # type: ignore[attr-defined]  # dynamic attr
    window._ui_inspector_window = inspector_window  # type: ignore[attr-defined]  # dynamic attr