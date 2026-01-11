import logging

from PyQt6.QtCore import QObject, QPoint, QTimer, Qt
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

    def _schedule_load_when_stable(self, image_paths: list[str], slot_num: int, delay_ms: int = 100):
        def _try_load():

            is_stable = bool(getattr(self.main_window, "_is_ui_stable", True)) and self.main_window.isVisible()
            if not is_stable:
                QTimer.singleShot(delay_ms, _try_load)
                return
            if self.main_controller and self.main_controller.session_ctrl:
                self.main_controller.session_ctrl.load_images_from_paths(image_paths, slot_num)
            self._first_external_load_pending = False

        if self._first_external_load_pending:
            QTimer.singleShot(delay_ms, _try_load)
        else:
            QTimer.singleShot(0, _try_load)

    def handle_drag_enter(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()

            QTimer.singleShot(0, lambda: self._safe_update_drag_overlays(True))
        else:
            event.ignore()

    def _safe_update_drag_overlays(self, visible):
        if self.ui is not None and hasattr(self.ui, 'update_drag_overlays'):
            try:
                self.ui.update_drag_overlays(self.store.viewport.is_horizontal, visible=visible)
            except (AttributeError, RuntimeError) as e:
                logger.warning(f"WindowEventHandler._safe_update_drag_overlays: failed to update drag overlays: {e}")

    def handle_drag_move(self, event: QDragMoveEvent):
        if event.mimeData().hasUrls():

            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def handle_drag_leave(self, event):
        self.ui.update_drag_overlays(visible=False)
        event.accept()

    def handle_drop(self, event: QDropEvent):

        QTimer.singleShot(0, lambda: self._safe_update_drag_overlays(False))

        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()

            image_paths = [url.toLocalFile() for url in urls if url.isLocalFile()]

            if not image_paths:
                event.ignore()
                return

            pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
            slot = 1 if self._is_in_left_area(pos) else 2

            event.acceptProposedAction()

            QTimer.singleShot(150, lambda: self.main_controller.session_ctrl.load_images_from_paths(image_paths, slot) if self.main_controller and self.main_controller.session_ctrl else None)
        else:
            event.ignore()

    def handle_resize(self, event):

        self.ui.update_drag_overlays(
            self.store.viewport.is_horizontal,
            self.ui.drag_overlay1.isVisible()
        )

    def handle_close(self, event):
        self.main_window.thread_pool.waitForDone()
        event.accept()

    def _is_in_left_area(self, pos: QPoint) -> bool:
        if not self.ui.image_label.isVisible(): return True
        label_rect = self.ui.image_label.geometry()

        if not self.store.viewport.is_horizontal:

            mid_x = label_rect.x() + label_rect.width() / 2
            return pos.x() < mid_x
        else:

            mid_y = label_rect.y() + label_rect.height() / 2
            return pos.y() < mid_y
