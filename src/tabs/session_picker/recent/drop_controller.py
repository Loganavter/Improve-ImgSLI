"""External .imgsli drop handling for the Recent shelf."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QWidget

from tabs.session_picker.recent.mime import (
    mime_has_external_project,
    project_paths_from_mime,
)


class RecentDropController(QObject):
    """Accepts project file drops on the shelf and related child widgets."""

    def __init__(
        self,
        host: QWidget,
        *,
        on_paths: Callable[[list[str]], None],
        on_active_changed: Callable[[bool], None],
    ) -> None:
        super().__init__(host)
        self._host = host
        self._on_paths = on_paths
        self._on_active_changed = on_active_changed
        self.drag_active = False

    def install(self, widgets: Iterable[QWidget | None]) -> None:
        for widget in widgets:
            if widget is None:
                continue
            widget.setAcceptDrops(True)
            widget.installEventFilter(self)

    def set_drag_active(self, active: bool) -> None:
        active = bool(active)
        if self.drag_active == active:
            return
        self.drag_active = active
        self._on_active_changed(active)

    def handle_drag_enter(self, event: QDragEnterEvent) -> None:
        if not mime_has_external_project(event):
            event.ignore()
            return
        event.acceptProposedAction()
        event.accept()
        self.set_drag_active(True)

    def handle_drag_move(self, event: QDragMoveEvent) -> None:
        if not mime_has_external_project(event):
            event.ignore()
            return
        event.acceptProposedAction()
        event.accept()

    def handle_drag_leave(self, event: QDragLeaveEvent) -> None:
        self.set_drag_active(False)
        event.accept()

    def handle_drop(self, event: QDropEvent) -> None:
        self.set_drag_active(False)
        if not mime_has_external_project(event):
            event.ignore()
            return
        paths = project_paths_from_mime(event.mimeData())
        event.acceptProposedAction()
        event.accept()
        if not paths:
            return
        # Defer pin+refresh so the drop source is released first.
        QTimer.singleShot(0, lambda: self._on_paths(list(paths)))

    def eventFilter(self, obj, event):  # noqa: N802
        et = event.type()
        if et == QEvent.Type.DragEnter:
            self.handle_drag_enter(event)
            return event.isAccepted()
        if et == QEvent.Type.DragMove:
            self.handle_drag_move(event)
            return event.isAccepted()
        if et == QEvent.Type.DragLeave:
            self.handle_drag_leave(event)
            return True
        if et == QEvent.Type.Drop:
            self.handle_drop(event)
            return event.isAccepted()
        return super().eventFilter(obj, event)
