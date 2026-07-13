from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QWidget

logger = logging.getLogger("ImproveImgSLI")

from devtools.ui_inspector.overlay import InspectorOverlay
from devtools.ui_inspector.panel import InspectorPanel
from devtools.ui_inspector.qss_index import QssIndex
from devtools.ui_inspector.widget_snapshot import inspect_widget


class UiInspectorController(QObject):
    def __init__(self, app: QApplication, window: QWidget, theme_manager):
        super().__init__(window)
        self._app = app
        self._window = window
        self._theme_manager = theme_manager
        self._qss_index = QssIndex.from_theme_manager(theme_manager)
        self._overlays: dict[QWidget, InspectorOverlay] = {}
        self._active_overlay: InspectorOverlay | None = None
        self._panel = InspectorPanel()
        self._enabled = True
        self._committed_widget: QWidget | None = None
        self._hover_widget: QWidget | None = None
        self._shift_held = False
        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(30)
        self._hover_timer.timeout.connect(self._poll_hover)
        self._panel.toggle_native_window_requested.connect(
            self._toggle_native_window
        )
        self._panel.force_repaint_requested.connect(self._force_repaint)
        self._panel.force_update_requested.connect(self._force_update)
        self._app.installEventFilter(self)

    def shutdown(self) -> None:
        self._hover_timer.stop()
        self._app.removeEventFilter(self)
        for window, overlay in self._overlays.items():
            try:
                window.removeEventFilter(self)
            except RuntimeError:
                pass
            overlay.hide()
            overlay.deleteLater()
        self._overlays.clear()
        self._active_overlay = None
        self._panel.hide()
        self._panel.deleteLater()

    def eventFilter(self, obj, event) -> bool:
        event_type = event.type()
        if event_type == QEvent.Type.KeyPress and self._handle_key_press(event):
            return True
        if event_type == QEvent.Type.KeyRelease:
            self._handle_key_release(event)
        if event_type in {
            QEvent.Type.Close,
            QEvent.Type.DeferredDelete,
        } and isinstance(obj, QWidget):
            overlay = self._overlays.pop(obj, None)
            if overlay is not None and overlay is self._active_overlay:
                self._active_overlay = None
            return False
        if event_type == QEvent.Type.Resize and isinstance(obj, QWidget):
            self._sync_overlay_for(obj)
            return False
        if not self._enabled:
            return False
        if event_type == QEvent.Type.MouseButtonPress:
            if self._handle_mouse_press(event):
                return True
        return False

    def _handle_key_press(self, event) -> bool:
        modifiers = event.modifiers()
        key = event.key()
        if (
            key == Qt.Key.Key_I
            and modifiers & Qt.KeyboardModifier.ControlModifier
            and modifiers & Qt.KeyboardModifier.ShiftModifier
        ):
            self._enabled = not self._enabled
            if self._enabled:
                self._refresh_overlay()
                if self._committed_widget is not None:
                    self._panel.show()
                    self._panel.raise_()
            else:
                self._shift_held = False
                self._hover_timer.stop()
                self._hover_widget = None
                self._hide_overlays()
                self._panel.hide()
            return True
        if key == Qt.Key.Key_Escape and self._enabled:
            self._committed_widget = None
            self._hover_widget = None
            self._clear_active_overlay()
            return True
        if self._enabled and key == Qt.Key.Key_Shift and not self._shift_held:
            self._shift_held = True
            self._hover_timer.start()
            self._poll_hover()
        return False

    def _handle_key_release(self, event) -> None:
        if event.key() != Qt.Key.Key_Shift:
            return
        self._shift_held = False
        self._hover_timer.stop()
        if self._hover_widget is not None:
            self._hover_widget = None
            self._refresh_overlay()

    def _handle_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        global_pos = _event_global_pos(event)
        widget = QApplication.widgetAt(global_pos)
        if widget is not None and self._is_inspector_widget(widget):
            return False
        if not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            if self._committed_widget is not None or self._hover_widget is not None:
                self._committed_widget = None
                self._hover_widget = None
                self._clear_active_overlay()
            return False
        widget = _resolve_meaningful_widget(widget)
        if widget is None:
            return False
        if widget.window() is self._panel:
            return False
        self._select_widget(widget, global_pos=global_pos)
        return True

    def _select_widget(self, widget: QWidget, *, global_pos: QPoint) -> None:
        self._committed_widget = widget
        self._hover_widget = None
        self._refresh_overlay()
        snapshot = inspect_widget(widget, self._theme_manager)
        self._panel.set_snapshot(
            snapshot,
            self._qss_index.candidates_for(widget),
            global_pos=global_pos,
        )

    def _toggle_native_window(self) -> None:
        widget = self._committed_widget
        if widget is None:
            return
        snapshot = inspect_widget(widget, self._theme_manager)
        if snapshot.window_has_qrhiwidget:
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
        self._resnapshot_committed()

    def _force_repaint(self) -> None:
        widget = self._committed_widget
        if widget is None:
            return
        widget.repaint()
        self._resnapshot_committed()

    def _force_update(self) -> None:
        widget = self._committed_widget
        if widget is None:
            return
        widget.update()
        self._resnapshot_committed()

    def _resnapshot_committed(self) -> None:
        widget = self._committed_widget
        if widget is None:
            return
        snapshot = inspect_widget(widget, self._theme_manager)
        self._panel.set_snapshot(snapshot, self._qss_index.candidates_for(widget))

    def _poll_hover(self) -> None:
        if not self._enabled or not self._shift_held:
            return
        pos = QCursor.pos()
        widget = QApplication.widgetAt(pos)
        if widget is not None and (
            self._is_inspector_widget(widget) or widget.window() is self._panel
        ):
            widget = None
        widget = _resolve_meaningful_widget(widget)
        if widget is self._hover_widget:
            return
        self._hover_widget = widget
        self._refresh_overlay()

    def _refresh_overlay(self) -> None:
        target = self._hover_widget or self._committed_widget
        if target is None:
            self._clear_active_overlay()
            return
        overlay = self._overlay_for(target.window())
        rect = _map_widget_rect(target, overlay.parentWidget())
        label = self._label_for(target)
        if self._active_overlay is not None and self._active_overlay is not overlay:
            self._active_overlay.clear_target()
            self._active_overlay.hide()
        self._active_overlay = overlay
        overlay.set_target(rect, label)

    def _clear_active_overlay(self) -> None:
        if self._active_overlay is not None:
            self._active_overlay.clear_target()
            self._active_overlay.hide()
            self._active_overlay = None

    def _label_for(self, widget: QWidget) -> str:
        object_name = widget.objectName()
        label = type(widget).__name__
        if object_name:
            label = f"{label}#{object_name}"
        return label

    def _is_inspector_widget(self, widget: QWidget) -> bool:
        current: QWidget | None = widget
        while current is not None:
            if bool(current.property("_ui_inspector_owned")):
                return True
            current = current.parentWidget()
        return False

    def _overlay_for(self, window: QWidget) -> InspectorOverlay:
        overlay = self._overlays.get(window)
        if overlay is None:
            overlay = InspectorOverlay(window)
            self._overlays[window] = overlay
            window.installEventFilter(self)
        overlay.setGeometry(window.rect())
        overlay.raise_()
        return overlay

    def _sync_overlay_for(self, widget: QWidget) -> None:
        overlay = self._overlays.get(widget)
        if overlay is None:
            return
        overlay.setGeometry(widget.rect())
        overlay.raise_()

    def _hide_overlays(self) -> None:
        for overlay in self._overlays.values():
            overlay.hide()
        self._active_overlay = None


def _event_global_pos(event) -> QPoint:
    if hasattr(event, "globalPosition"):
        return event.globalPosition().toPoint()
    return event.globalPos()


def _map_widget_rect(widget: QWidget, target_parent: QWidget):
    top_left = widget.mapTo(target_parent, QPoint(0, 0))
    return widget.rect().translated(top_left)


def _resolve_meaningful_widget(widget: QWidget | None) -> QWidget | None:
    current = widget
    while current is not None:
        name = current.objectName()
        if not name.startswith("qt_"):
            return current
        parent = current.parentWidget()
        if parent is None:
            return current
        current = parent
    return widget
