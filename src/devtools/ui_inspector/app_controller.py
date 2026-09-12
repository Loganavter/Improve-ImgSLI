"""App-side controller: toolkit InspectorController + native diagnostics
refresh + the three experiment actions (native window toggle / repaint /
update) + Dump layout (Find-Action-aware)."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.inspector.controller import InspectorController

from devtools.ui_inspector.app_window import AppInspectorWindow
from devtools.ui_inspector.native import native_chain, window_has_qrhiwidget
from devtools.ui_layout_dump import dump_ui_layout
from ui.actions.registry import get_action_registry

logger = logging.getLogger("ImproveImgSLI")


def _ancestor_chain(widget: QWidget) -> list[dict[str, str]]:
    """Parent chain from the top-level window down to ``widget`` itself —
    context for a subtree dump, without the siblings' layout noise."""
    chain: list[dict[str, str]] = []
    node: QWidget | None = widget
    while node is not None:
        chain.append({"class": type(node).__name__, "object_name": node.objectName()})
        node = node.parentWidget()
    return list(reversed(chain))


class AppInspectorController(InspectorController):
    def __init__(self, app: QApplication, window: AppInspectorWindow, theme_manager):
        super().__init__(app, window, theme_manager)
        window.dump_layout_requested.connect(self._dump_layout)
        window.dump_window_layout_requested.connect(self._dump_window_layout)
        window.toggle_native_window_requested.connect(self._toggle_native_window)
        window.force_repaint_requested.connect(self._force_repaint)
        window.force_update_requested.connect(self._force_update)

    # -- selection extends the toolkit behavior with native diagnostics -----

    def _select_widget(self, widget: QWidget, *, global_pos) -> None:
        from devtools.ui_inspector.theme_sources import token_sources

        self._token_sources = token_sources(self._theme_manager)
        super()._select_widget(widget, global_pos=global_pos)
        self._window.set_native_diagnostics(widget, tuple(native_chain(widget)))

    def _resnapshot(self) -> None:
        widget = self._committed_widget
        if widget is None:
            return
        self._select_widget(widget, global_pos=self._last_focused_global())

    @staticmethod
    def _last_focused_global():
        from PySide6.QtGui import QCursor

        return QCursor.pos()

    # -- experiment actions (ported from the legacy panel) -------------------

    def _toggle_native_window(self) -> None:
        widget = self._committed_widget
        if widget is None:
            return
        if window_has_qrhiwidget(widget):
            logger.warning(
                "DIAG ui_inspector refused WA_NativeWindow toggle on %s: "
                "top-level window contains a QRhiWidget; this has been "
                "observed to corrupt QRhiWidget rendering app-wide on "
                "Wayland with no clean undo. Restart required if this was "
                "already toggled once.",
                type(widget).__name__,
            )
            return
        currently_native = widget.testAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        widget.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, not currently_native)
        if not currently_native:
            widget.winId()
        logger.warning(
            "DIAG ui_inspector toggled WA_NativeWindow on %s: %s -> %s",
            type(widget).__name__,
            currently_native,
            not currently_native,
        )
        widget.repaint()
        self._resnapshot()

    def _force_repaint(self) -> None:
        widget = self._committed_widget
        if widget is None:
            return
        widget.repaint()
        self._resnapshot()

    def _force_update(self) -> None:
        widget = self._committed_widget
        if widget is None:
            return
        widget.update()
        self._resnapshot()

    def _dump_layout(self) -> None:
        target = (
            self._committed_widget
            or self._last_focused_window
            or QApplication.activeWindow()
        )
        data = dump_ui_layout(target, get_action_registry())
        if self._committed_widget is not None:
            data["path"] = _ancestor_chain(self._committed_widget)
        self._write_dump_file(target, data)

    def _dump_window_layout(self) -> None:
        target = self._last_focused_window or QApplication.activeWindow()
        self._write_dump_file(target, dump_ui_layout(target, get_action_registry()))

    def _write_dump_file(self, target: QWidget, data: dict) -> None:
        try:
            import json
            import tempfile
            from datetime import datetime
            from pathlib import Path

            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            out_path = Path(tempfile.gettempdir()) / (
                f"imgsli_ui_dump_{type(target).__name__}_{stamp}.json"
            )
            out_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception:
            logger.exception("UI Inspector: layout dump failed")
            self._window.show_dump_result("failed")
            return
        from PySide6.QtGui import QGuiApplication

        QGuiApplication.clipboard().setText(str(out_path))
        self._window.show_dump_result(str(out_path))
        logger.info(
            "UI Inspector: dumped %s layout to %s (path copied to clipboard)",
            type(target).__name__,
            out_path,
        )