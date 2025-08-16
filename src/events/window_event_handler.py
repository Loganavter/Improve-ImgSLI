from PyQt6.QtCore import Qt, QPoint, QTimer, QObject
from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QMouseEvent

class WindowEventHandler(QObject):
    def __init__(self, app_state, main_controller, ui, parent=None):
        super().__init__(parent)
        self.app_state = app_state
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
            self.main_controller.load_images_from_paths(image_paths, slot_num)
            self._first_external_load_pending = False
        if self._first_external_load_pending:
            QTimer.singleShot(delay_ms, _try_load)
        else:
            QTimer.singleShot(0, _try_load)

    def handle_drag_enter(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            try:
                if self.main_window.isVisible() and self.ui.image_label.isVisible():
                    self.ui.update_drag_overlays(self.app_state.is_horizontal, visible=True)
            except Exception:
                pass

    def handle_drag_move(self, event: QDragMoveEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def handle_drag_leave(self, event):
        self.ui.update_drag_overlays(visible=False)

    def handle_drop(self, event: QDropEvent):
        try:
            if hasattr(self.ui, 'update_drag_overlays'):
                self.ui.update_drag_overlays(visible=False)
        except Exception:
            pass
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            image_paths = [url.toLocalFile() for url in urls if url.isLocalFile()]
            if not image_paths:
                event.ignore()
                return
            try:
                drop_pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
            except Exception:
                drop_pos = None
            is_left = True if drop_pos is None else self._is_in_left_area(drop_pos)
            event.acceptProposedAction()
            self._schedule_load_when_stable(image_paths, 1 if is_left else 2, delay_ms=150)
        else:
            event.ignore()

    def handle_resize(self, event):
        if not self.app_state.resize_in_progress:
            self.app_state.resize_in_progress = True

        self.ui.update_drag_overlays(
            self.app_state.is_horizontal,
            self.ui.drag_overlay1.isVisible()
        )

        QTimer.singleShot(200, self._finish_resize_delay)

    def _finish_resize_delay(self):
        if self.app_state.resize_in_progress:
            self.app_state.resize_in_progress = False
            self.main_window.schedule_update()

    def handle_close(self, event):
        self.main_window.thread_pool.waitForDone()
        event.accept()

    def _is_in_left_area(self, pos: QPoint) -> bool:
        if not self.ui.image_label.isVisible(): return True
        label_rect = self.ui.image_label.geometry()
        if not self.app_state.is_horizontal:
            return pos.x() < label_rect.x() + label_rect.width() / 2
        else:
            return pos.y() < label_rect.y() + label_rect.height() / 2
