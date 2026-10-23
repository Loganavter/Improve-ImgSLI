"""External project-file drop handling for the Recent shelf."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import QEvent, QObject, QTimer


def _is_alive(obj) -> bool:
    """True while ``obj``'s C++ wrapper is still valid (singleShot may fire
    after the owner was deleted)."""
    try:
        import shiboken6

        return shiboken6.Shiboken.isValid(obj)
    except Exception:
        return True
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
        on_empty_drop: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(host)
        self._host = host
        self._on_paths = on_paths
        self._on_active_changed = on_active_changed
        self._on_empty_drop = on_empty_drop
        self.drag_active = False
        # Nested enter/leave balance: one controller is installed on the
        # panel AND its children (scroll, host, empty zone), so crossing a
        # child boundary fires leave+enter pairs mid-gesture. A plain bool
        # would flicker the highlight (or freeze it stuck) — active while
        # the depth is positive.
        self._drag_depth = 0

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

    def _sync_drag_active(self) -> None:
        """Apply the nested depth to the public flag (single change point)."""
        self.set_drag_active(self._drag_depth > 0)

    def handle_drag_enter(self, event: QDragEnterEvent) -> None:
        if not mime_has_external_project(event):
            event.ignore()
            return
        event.acceptProposedAction()
        event.accept()
        self._drag_depth += 1
        self._sync_drag_active()

    def handle_drag_move(self, event: QDragMoveEvent) -> None:
        if not mime_has_external_project(event):
            event.ignore()
            return
        event.acceptProposedAction()
        event.accept()

    def handle_drag_leave(self, event: QDragLeaveEvent) -> None:
        self._drag_depth = max(0, self._drag_depth - 1)
        self._sync_drag_active()
        event.accept()

    def handle_drop(self, event: QDropEvent) -> None:
        self._drag_depth = 0
        self.set_drag_active(False)
        if not mime_has_external_project(event):
            event.ignore()
            return
        paths = project_paths_from_mime(event.mimeData())
        event.acceptProposedAction()
        event.accept()
        if not paths:
            # Consumed but empty: never silent — the shelf reports the miss
            # (toast hint) instead of swallowing the gesture.
            try:
                if self._on_empty_drop is not None:
                    self._on_empty_drop()
            except Exception:
                pass
            return
        # Defer pin+refresh so the drop source is released first. The
        # singleShot is not parented to this controller: guard against the
        # controller being destroyed before it fires (a deleted C++ object
        # raises inside the event loop and poisons unrelated tests).
        QTimer.singleShot(
            0,
            lambda: self._on_paths(list(paths))
            if _is_alive(self)
            else None,
        )

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