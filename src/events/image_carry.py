"""Move an image under the cursor (DragGhost) for click-to-deliver to another tab.

Distinct from flyout-row :class:`~events.drag_drop_handler.DragAndDropService`
(list reorder/move). This path is file-path based and finishes on a workspace
tab click or a canvas drop, then starts the tab's pending-insert UX (paste
direction / placement highlight) — the same flow as Duplicate / DnD paste.
"""

from __future__ import annotations

import logging
from pathlib import Path

import shiboken6 as sip
from PySide6.QtCore import QObject, QPoint, QPointF, Qt
from PySide6.QtGui import QCursor, QPixmap
from PySide6.QtWidgets import QApplication
from shared_toolkit.ui.overlay_layer import get_overlay_layer

logger = logging.getLogger("ImproveImgSLI")

_PREVIEW_WIDTH = 160
# Cursor sits near the ghost's top-right so the preview hangs bottom-left.
_GHOST_HOTSPOT_INSET = 12


class ImageCarryService(QObject):
    _instance: "ImageCarryService | None" = None

    @classmethod
    def get_instance(cls) -> "ImageCarryService":
        if cls._instance is None:
            raise RuntimeError(
                "ImageCarryService has not been initialized. "
                "Call ImageCarryService(store, parent) once during compose."
            )
        return cls._instance

    def __init__(self, store, parent=None):
        if ImageCarryService._instance is not None:
            raise RuntimeError("ImageCarryService is a singleton; use get_instance().")
        super().__init__(parent)
        ImageCarryService._instance = self
        self.store = store
        self.main_window = parent
        self._active = False
        self._armed = False
        self._arm_origin = QPoint()
        self._paths: list[Path] = []
        self._ghost_widget = None
        self._hotspot = QPointF()
        self._tab_hint = None

    def is_active(self) -> bool:
        return self._active

    def begin(
        self,
        paths: list[str | Path],
        *,
        pixmap: QPixmap | None = None,
        hotspot: QPointF | None = None,
    ) -> bool:
        """Start Move mode. Returns False if paths/preview are unusable."""
        if self._active:
            self.cancel()

        resolved = [Path(p) for p in paths if p]
        resolved = [p for p in resolved if p.is_file()]
        if not resolved:
            logger.warning("ImageCarryService.begin: no existing file paths")
            return False

        preview = pixmap
        if preview is None or preview.isNull():
            preview = preview_pixmap_for_path(resolved[0])
        if preview is None or preview.isNull():
            logger.warning("ImageCarryService.begin: could not build preview")
            return False

        try:
            from events.drag_drop_handler import DragAndDropService

            dnd = DragAndDropService.get_instance()
            if dnd.is_dragging():
                dnd.cancel_drag()
        except Exception:
            pass

        self._paths = resolved
        self._active = True
        self._armed = False
        cursor = QCursor.pos()
        self._arm_origin = QPoint(cursor)
        if hotspot is None:
            inset = float(_GHOST_HOTSPOT_INSET)
            self._hotspot = QPointF(
                max(inset, float(preview.width()) - inset),
                inset,
            )
        else:
            self._hotspot = QPointF(hotspot)

        from sli_ui_toolkit.widgets import DragGhostWidget

        ghost_parent = None
        if self.main_window is not None:
            overlay = get_overlay_layer(self.main_window)
            ghost_parent = overlay.host if overlay is not None else self.main_window
        if ghost_parent is None:
            self._active = False
            self._paths = []
            return False

        self._ghost_widget = DragGhostWidget(ghost_parent)
        self._ghost_widget.set_pixmap(preview)
        self._ghost_widget.setOpacity(0.85)
        self._move_ghost(cursor)
        self._ghost_widget.show()
        self._ghost_widget.raise_()
        self._start_tab_hint()
        return True

    def update_position(self, event) -> None:
        if not self._active or self._ghost_widget is None:
            return
        global_pos = event.globalPosition().toPoint()
        if not self._armed:
            delta = global_pos - self._arm_origin
            threshold = QApplication.startDragDistance()
            if delta.manhattanLength() >= threshold:
                self._armed = True
        self._move_ghost(global_pos)
        if self._tab_hint is not None:
            self._tab_hint.update_hover(global_pos)

    def finish(self, event) -> None:
        if not self._active:
            return
        # Swallow the mouse-release that closes the context menu so we do not
        # immediately drop onto the canvas under the menu.
        if not self._armed:
            return
        global_pos = event.globalPosition().toPoint()
        delivered = self._try_deliver(global_pos)
        if delivered:
            self._cleanup()
        # Non-target click keeps the ghost so the user can try again.

    def cancel(self) -> None:
        if not self._active:
            return
        self._cleanup()

    def _move_ghost(self, global_pos: QPoint) -> None:
        if self._ghost_widget is None or not sip.isValid(self._ghost_widget):
            return
        top_left = global_pos - self._hotspot.toPoint()
        self._ghost_widget.move(top_left)
        self._ghost_widget.raise_()

    def _start_tab_hint(self) -> None:
        try:
            from ui.main_window.workspace_tab_carry_hint import WorkspaceTabCarryHint

            hint = WorkspaceTabCarryHint()
            hint.start(self.main_window, self.store, list(self._paths))
            self._tab_hint = hint
        except Exception:
            logger.exception("ImageCarry: tab hint failed to start")
            self._tab_hint = None

    def _try_deliver(self, global_pos: QPoint) -> bool:
        if self._try_deliver_to_workspace_tab(global_pos):
            return True
        return self._try_deliver_to_active_canvas(global_pos)

    def _try_deliver_to_workspace_tab(self, global_pos: QPoint) -> bool:
        window = self.main_window
        ui = getattr(window, "ui", None) if window is not None else None
        tabs = getattr(ui, "workspace_tabs", None) if ui is not None else None
        if tabs is None:
            return False
        tab_bar = getattr(tabs, "tab_bar", None)
        if tab_bar is None:
            return False
        local = tab_bar.mapFromGlobal(global_pos)
        if not tab_bar.rect().contains(local):
            return False
        index = tab_bar.tabAt(local)
        if index < 0:
            return False
        session_id = tabs.tabData(index)
        if not session_id:
            return False

        session = self.store.get_workspace_session(session_id)
        if session is None:
            return False
        session_type = getattr(session, "session_type", "") or ""

        from tabs.registry import TabRegistry

        registry = TabRegistry()
        tab = registry.get_tab(session_type)
        if tab is None or not tab.accepts_drop(self._paths):
            return False

        active_id = getattr(self.store.workspace, "active_session_id", None)
        if session_id != active_id:
            switched = self._switch_session(session_id, index)
            if not switched and self.store.get_workspace_session(session_id) is None:
                return False

        # Defer until tab page / controller are active after the switch.
        from PySide6.QtCore import QTimer

        paths = list(self._paths)
        QTimer.singleShot(
            0,
            lambda st=session_type, ps=paths: _schedule_pending_insert(st, ps),
        )
        return True

    def _switch_session(self, session_id: str, tab_index: int) -> bool:
        window = self.main_window
        presenter = getattr(window, "presenter", None) if window is not None else None
        controller = (
            getattr(presenter, "main_controller", None) if presenter is not None else None
        )
        workspace = getattr(controller, "workspace", None) if controller else None
        if workspace is not None and hasattr(workspace, "switch_workspace_session"):
            try:
                workspace.switch_workspace_session(session_id)
                return True
            except Exception:
                logger.exception("ImageCarry: switch_workspace_session failed")
        # Fallback: drive the tab strip (emits currentChanged → same path).
        ui = getattr(window, "ui", None) if window is not None else None
        tabs = getattr(ui, "workspace_tabs", None) if ui is not None else None
        if tabs is not None and tab_index >= 0:
            tabs.setCurrentIndex(tab_index)
            return True
        try:
            return bool(self.store.switch_workspace_session(session_id))
        except Exception:
            logger.exception("ImageCarry: store switch failed")
            return False

    def _try_deliver_to_active_canvas(self, global_pos: QPoint) -> bool:
        session = self.store.get_active_workspace_session()
        if session is None:
            return False
        session_type = getattr(session, "session_type", "") or ""
        from tabs.registry import TabRegistry

        registry = TabRegistry()
        tab = registry.get_tab(session_type)
        if tab is None or not tab.accepts_drop(self._paths):
            return False

        widget_at = QApplication.widgetAt(global_pos)
        if widget_at is None:
            return False
        if not self._widget_belongs_to_active_canvas(tab, widget_at):
            return False

        return _schedule_pending_insert(session_type, list(self._paths))

    def _widget_belongs_to_active_canvas(self, tab, widget) -> bool:
        if hasattr(tab, "owns_widget") and tab.owns_widget(widget):
            return True
        page = None
        try:
            from tabs.registry import TabRegistry

            page = TabRegistry().get_page(tab.session_type)
        except Exception:
            page = None
        if page is None:
            return False
        w = widget
        while w is not None:
            if w is page:
                return True
            w = w.parentWidget() if hasattr(w, "parentWidget") else None
        return False

    def _cleanup(self) -> None:
        if self._tab_hint is not None:
            try:
                self._tab_hint.stop()
            except Exception:
                pass
            self._tab_hint = None
        if self._ghost_widget is not None:
            try:
                if sip.isValid(self._ghost_widget):
                    self._ghost_widget.deleteLater()
            except RuntimeError:
                pass
            self._ghost_widget = None
        self._active = False
        self._armed = False
        self._arm_origin = QPoint()
        self._paths = []
        self._hotspot = QPointF()


def _schedule_pending_insert(session_type: str, paths: list[Path]) -> bool:
    """Start tab-owned insert UX; fall back to route_drop if unimplemented."""
    from tabs.registry import TabRegistry

    registry = TabRegistry()
    try:
        started = registry.create_service_for(
            session_type, "begin_pending_image_insert", paths
        )
        if started:
            return True
    except Exception:
        logger.exception(
            "ImageCarry: begin_pending_image_insert failed for %s", session_type
        )
    return bool(registry.route_drop(session_type, paths))


def preview_pixmap_for_path(path: Path, *, width: int = _PREVIEW_WIDTH) -> QPixmap:
    pix = QPixmap(str(path))
    if pix.isNull():
        return pix
    return pix.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)


def preview_pixmap_from_pixel_source(image, *, width: int = _PREVIEW_WIDTH) -> QPixmap:
    if image is None:
        return QPixmap()
    try:
        from shared.image_processing.tiled_pixel_store import qimage_from_pixel_source

        qimg = qimage_from_pixel_source(image)
        return QPixmap.fromImage(qimg).scaledToWidth(
            width, Qt.TransformationMode.SmoothTransformation
        )
    except Exception:
        logger.exception("preview_pixmap_from_pixel_source failed")
        return QPixmap()


def begin_image_carry(
    paths: list[str | Path],
    *,
    image=None,
    pixmap: QPixmap | None = None,
) -> bool:
    """Convenience entry for context menus (resolves the singleton)."""
    try:
        service = ImageCarryService.get_instance()
    except RuntimeError:
        logger.warning("ImageCarryService unavailable")
        return False
    preview = pixmap
    if (preview is None or preview.isNull()) and image is not None:
        preview = preview_pixmap_from_pixel_source(image)
    return service.begin(paths, pixmap=preview)
