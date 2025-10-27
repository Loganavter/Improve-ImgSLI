import logging
from PyQt6 import sip
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPointF, QEvent, pyqtSignal, QObject, QTimer, QPoint

DragGhostWidget = None

logger = logging.getLogger("ImproveImgSLI")

class DragAndDropService(QObject):
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            raise RuntimeError("DragAndDropService has not been initialized yet. Call DragAndDropService(app_ref, parent) once.")
        return cls._instance

    def __init__(self, app_ref, parent=None):
        if DragAndDropService._instance is not None:
            raise RuntimeError("This class is a singleton! Use get_instance().")
        super().__init__(parent)
        DragAndDropService._instance = self

        self.app_ref = app_ref
        self.app_state = app_ref.app_state

        self._is_dragging = False
        self._source_data = None
        self._ghost_widget = None
        self._drag_start_pos_global = QPointF()
        self._hotspot = QPointF()
        self._current_target = None
        self._source_widget = None
        self._drop_targets = []

    def register_drop_target(self, target):
        if target not in self._drop_targets:
            self._drop_targets.append(target)

    def unregister_drop_target(self, target):
        if target in self._drop_targets:
            self._drop_targets.remove(target)

    def is_dragging(self):
        return self._is_dragging

    def start_drag(self, source_widget, event):
        global DragGhostWidget

        if self._is_dragging:
            return

        self._is_dragging = True

        try:
            from ui.widgets.custom_widgets import PathTooltip
            PathTooltip.get_instance().hide_tooltip()
        except Exception:
            pass

        self._source_widget = source_widget

        list_num = source_widget.owner_flyout.image_number
        index = source_widget.index
        target_list = self.app_ref.app_state.image_list1 if list_num == 1 else self.app_ref.app_state.image_list2
        current_rating = 0
        if 0 <= index < len(target_list):
            current_rating = target_list[index][3]

        self._source_data = {
            "list_num": list_num,
            "index": index,
            "rating_backup": current_rating,
        }

        self._drag_start_pos_global = event.globalPosition()
        self._hotspot = event.position()

        pixmap = source_widget.grab()

        if DragGhostWidget is None:
            from ui.widgets.composite.drag_ghost_widget import DragGhostWidget

        self._ghost_widget = DragGhostWidget()
        self._ghost_widget.set_pixmap(pixmap)

        desired_top_left_global = event.globalPosition().toPoint() - self._hotspot.toPoint()

        self._ghost_widget.move(desired_top_left_global)
        self._ghost_widget.show()
        self._ghost_widget.raise_()

        if hasattr(self._source_widget, 'set_dragging_state'):
            self._source_widget.set_dragging_state(True)

    def update_drag_position(self, event):
        if not self._is_dragging or not self._ghost_widget:
            return

        current_pos_global = event.globalPosition()

        if self._ghost_widget and not sip.isdeleted(self._ghost_widget):
            desired_top_left_global = current_pos_global.toPoint() - self._hotspot.toPoint()
            self._ghost_widget.move(desired_top_left_global)

        try:
            ui_manager = self.app_ref.presenter.ui_manager if hasattr(self.app_ref, 'presenter') else None
            unified = ui_manager.unified_flyout if ui_manager else None
            if unified and unified.isVisible() and unified.mode.name.startswith('SINGLE'):
                rect = unified.frameGeometry()
                if not rect.contains(current_pos_global.toPoint()):
                    unified.switchToDoubleMode()
        except Exception:
            pass

        new_target = None
        for target in reversed(self._drop_targets):
            if target.isVisible():
                local_pos = target.mapFromGlobal(current_pos_global.toPoint())
                if target.rect().contains(local_pos):
                    new_target = target
                    break

        if self._current_target != new_target:
            if self._current_target and hasattr(self._current_target, 'clear_drop_indicator'):
                self._current_target.clear_drop_indicator()
            self._current_target = new_target

        if self._current_target and hasattr(self._current_target, 'can_accept_drop'):
            can_accept = self._current_target.can_accept_drop(self._source_data)
            if can_accept:
                if hasattr(self._current_target, 'update_drop_indicator'):
                    self._current_target.update_drop_indicator(current_pos_global)
            else:
                 if hasattr(self._current_target, 'clear_drop_indicator'):
                    self._current_target.clear_drop_indicator()

    def finish_drag(self, event):
        if not self._is_dragging:
            return

        current_pos_global = event.globalPosition()
        final_target = self._current_target

        if final_target and hasattr(final_target, 'can_accept_drop') and final_target.can_accept_drop(self._source_data):
            if hasattr(final_target, 'handle_drop'):
                final_target.handle_drop(self._source_data, current_pos_global)

        self._cleanup()

    def cancel_drag(self):
        if not self._is_dragging:
            return

        self._cleanup()

    def _cleanup(self):

        if self._ghost_widget:
            self._ghost_widget.deleteLater()
            self._ghost_widget = None

        if self._source_widget and not sip.isdeleted(self._source_widget):
            try:
                if hasattr(self._source_widget, 'set_dragging_state'):
                    self._source_widget.set_dragging_state(False)
            except RuntimeError:
                pass

        if self._current_target and not sip.isdeleted(self._current_target):
            try:
                if hasattr(self._current_target, 'clear_drop_indicator'):
                    self._current_target.clear_drop_indicator()
            except RuntimeError:
                pass

        self._is_dragging = False
        self._source_data = None
        self._current_target = None
        self._source_widget = None
