import logging

from PyQt6.QtCore import QObject, QPoint, Qt, QTimer
from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent

logger = logging.getLogger("ImproveImgSLI")

class WindowEventHandler(QObject):
    def __init__(self, store, main_controller, ui, parent=None):
        super().__init__(parent)
        self.store = store

        self.main_controller = main_controller
        self.ui = ui
        self.main_window = parent
        self._first_external_load_pending = True
        self._drag_leave_timer = QTimer(self)
        self._drag_leave_timer.setSingleShot(True)
        self._drag_leave_timer.setInterval(80)
        self._drag_leave_timer.timeout.connect(self._handle_deferred_drag_leave)

    def _schedule_load_when_stable(
        self, image_paths: list[str], slot_num: int, delay_ms: int = 100
    ):
        def _try_load():

            is_stable = (
                bool(getattr(self.main_window, "_is_ui_stable", True))
                and self.main_window.isVisible()
            )
            if not is_stable:
                QTimer.singleShot(delay_ms, _try_load)
                return
            if self.main_controller and self.main_controller.sessions:
                self.main_controller.sessions.load_images_from_paths(
                    image_paths, slot_num
                )
            self._first_external_load_pending = False

        if self._first_external_load_pending:
            QTimer.singleShot(delay_ms, _try_load)
        else:
            QTimer.singleShot(0, _try_load)

    def handle_drag_enter(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            self._drag_leave_timer.stop()
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()

            QTimer.singleShot(0, lambda: self._safe_update_drag_overlays(True))
        else:
            event.ignore()

    def _safe_update_drag_overlays(self, visible):
        if self.ui is not None and hasattr(self.ui, "update_drag_overlays"):
            try:
                self.ui.update_drag_overlays(
                    self.store.viewport.view_state.is_horizontal, visible=visible
                )
            except (AttributeError, RuntimeError) as e:
                logger.warning(
                    f"WindowEventHandler._safe_update_drag_overlays: failed to update drag overlays: {e}"
                )

    def handle_drag_move(self, event: QDragMoveEvent):
        if event.mimeData().hasUrls():
            self._drag_leave_timer.stop()
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def handle_drag_leave(self, event):
        self._drag_leave_timer.start()
        event.accept()

    def handle_drop(self, event: QDropEvent):
        self._drag_leave_timer.stop()
        QTimer.singleShot(0, lambda: self._safe_update_drag_overlays(False))

        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()

            image_paths = [url.toLocalFile() for url in urls if url.isLocalFile()]

            if not image_paths:
                event.ignore()
                return

            pos = (
                event.position().toPoint()
                if hasattr(event, "position")
                else event.pos()
            )
            slot = 1 if self._is_in_left_area(pos) else 2

            event.acceptProposedAction()

            QTimer.singleShot(
                150,
                lambda: (
                    self.main_controller.sessions.load_images_from_paths(
                        image_paths, slot
                    )
                    if self.main_controller and self.main_controller.sessions
                    else None
                ),
            )
        else:
            event.ignore()

    def handle_resize(self, event):
        self.ui.update_drag_overlays(
            self.store.viewport.view_state.is_horizontal, self.ui.is_drag_overlay_visible()
        )

    def handle_close(self, event):
        event.accept()

    def _is_in_left_area(self, pos: QPoint) -> bool:
        if not self.ui.image_label.isVisible():
            return True
        label_rect = self.ui.image_label.geometry()

        if not self.store.viewport.view_state.is_horizontal:

            mid_x = label_rect.x() + label_rect.width() / 2
            return pos.x() < mid_x
        else:

            mid_y = label_rect.y() + label_rect.height() / 2
            return pos.y() < mid_y

    def _handle_deferred_drag_leave(self):
        self._safe_update_drag_overlays(False)
