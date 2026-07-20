import logging

import shiboken6 as sip
from PySide6.QtCore import QObject, QPointF, QTimer
from ui.widgets.drag_ghost_widget import DragGhostWidget, make_count_slot_pixmap
from shared_toolkit.ui.overlay_layer import get_overlay_layer

logger = logging.getLogger("ImproveImgSLI")

class DragAndDropService(QObject):
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            raise RuntimeError(
                "DragAndDropService has not been initialized yet. Call DragAndDropService(store, parent) once."
            )
        return cls._instance

    def __init__(self, store, parent=None):
        if DragAndDropService._instance is not None:
            raise RuntimeError("This class is a singleton! Use get_instance().")
        super().__init__(parent)
        DragAndDropService._instance = self

        self.store = store
        self.main_window = parent

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

    def get_source_data(self):
        if not self._source_data:
            return None
        try:
            return dict(self._source_data)
        except Exception:
            return self._source_data

    def start_drag(self, source_widget, event):
        if self._is_dragging:
            return

        try:
            from sli_ui_toolkit.ui.widgets.atomic.tooltips import PathTooltip

            PathTooltip.get_instance().hide_tooltip()
        except Exception:
            pass

        self._source_widget = source_widget

        list_num = getattr(source_widget, "list_num", None)
        if list_num not in (1, 2):
            list_num = getattr(source_widget, "image_number", None)
        if list_num not in (1, 2):
            owner_flyout = getattr(source_widget, "owner_flyout", None)
            list_num = getattr(owner_flyout, "image_number", None)
        index = getattr(source_widget, "index", -1)
        if list_num not in (1, 2) or index < 0:
            logger.warning(
                "[DragAndDrop] start_drag skipped for unsupported source widget: type=%s list_num=%r index=%r",
                type(source_widget).__name__,
                list_num,
                index,
            )
            self._source_widget = None
            return

        indices_fn = getattr(source_widget, "drag_indices", None)
        if callable(indices_fn):
            try:
                indices = [int(i) for i in indices_fn() if isinstance(i, int) and i >= 0]
            except Exception:
                indices = [index]
        else:
            indices = [index]
        if not indices:
            indices = [index]
        indices = sorted(set(indices))

        self._is_dragging = True

        document = self.store.get_session_state_slot("document")
        target_list = (
            document.image_list1 if list_num == 1 else document.image_list2
        )
        current_rating = 0
        if 0 <= index < len(target_list):
            current_rating = target_list[index].rating

        self._source_data = {
            "list_num": list_num,
            "index": index,
            "indices": indices,
            "rating_backup": current_rating,
        }

        self._drag_start_pos_global = event.globalPosition()
        self._hotspot = event.position()

        if len(indices) > 1:
            pixmap = make_count_slot_pixmap(source_widget, len(indices))
            # Center hotspot on the badge slot.
            self._hotspot = QPointF(pixmap.width() / 2.0, pixmap.height() / 2.0)
        else:
            pixmap = source_widget.grab()

        ghost_parent = None
        if self.main_window is not None:
            overlay = get_overlay_layer(self.main_window)
            ghost_parent = overlay.host if overlay is not None else self.main_window

        self._ghost_widget = DragGhostWidget(ghost_parent)
        self._ghost_widget.set_pixmap(pixmap)

        desired_top_left_global = (
            event.globalPosition().toPoint() - self._hotspot.toPoint()
        )

        self._ghost_widget.move(desired_top_left_global)
        self._ghost_widget.show()
        self._ghost_widget.raise_()

        if hasattr(self._source_widget, "set_batch_dragging_state"):
            try:
                self._source_widget.set_batch_dragging_state(True, indices)
            except Exception:
                if hasattr(self._source_widget, "set_dragging_state"):
                    self._source_widget.set_dragging_state(True)
        elif hasattr(self._source_widget, "set_dragging_state"):
            self._source_widget.set_dragging_state(True)

    def update_drag_position(self, event):
        if not self._is_dragging or not self._ghost_widget:
            return

        current_pos_global = event.globalPosition()

        if self._ghost_widget and sip.isValid(self._ghost_widget):
            desired_top_left_global = (
                current_pos_global.toPoint() - self._hotspot.toPoint()
            )
            self._ghost_widget.move(desired_top_left_global)
            self._ghost_widget.raise_()

        try:
            ui_manager = None
            if self.main_window and hasattr(self.main_window, "presenter"):
                ui_manager = self.main_window.presenter.ui_manager

            unified = ui_manager.unified_flyout if ui_manager else None

            if (
                unified
                and unified.isVisible()
                and unified.mode.name.startswith("SINGLE")
            ):
                parent_widget = unified.parent()
                if parent_widget:
                    local_pos = parent_widget.mapFromGlobal(
                        current_pos_global.toPoint()
                    )
                    unified_geom = unified.geometry()
                    contains = unified_geom.contains(local_pos)
                    if not contains:
                        unified.switchToDoubleMode()
        except Exception as e:
            logger.exception(
                f"[DragAndDrop] update_drag_position: исключение при проверке переключения в DOUBLE режим: {e}"
            )

        new_target = None
        for target in reversed(self._drop_targets):
            if target.isVisible():
                local_pos = target.mapFromGlobal(current_pos_global.toPoint())
                if target.rect().contains(local_pos):
                    new_target = target
                    break

        if self._current_target != new_target:
            if self._current_target and hasattr(
                self._current_target, "clear_drop_indicator"
            ):
                self._current_target.clear_drop_indicator()
            self._current_target = new_target

        if self._current_target and hasattr(self._current_target, "can_accept_drop"):
            can_accept = self._current_target.can_accept_drop(self._source_data)
            if can_accept:
                if hasattr(self._current_target, "update_drop_indicator"):
                    self._current_target.update_drop_indicator(current_pos_global)
            else:
                if hasattr(self._current_target, "clear_drop_indicator"):
                    self._current_target.clear_drop_indicator()

    def finish_drag(self, event):
        if not self._is_dragging:
            return

        current_pos_global = event.globalPosition()
        final_target = self._current_target

        if (
            final_target
            and hasattr(final_target, "can_accept_drop")
            and final_target.can_accept_drop(self._source_data)
        ):
            if hasattr(final_target, "handle_drop"):
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

        if self._source_widget and sip.isValid(self._source_widget):
            try:
                indices = []
                if isinstance(self._source_data, dict):
                    indices = list(self._source_data.get("indices") or [])
                if hasattr(self._source_widget, "set_batch_dragging_state"):
                    self._source_widget.set_batch_dragging_state(False, indices)
                elif hasattr(self._source_widget, "set_dragging_state"):
                    self._source_widget.set_dragging_state(False)
            except RuntimeError:
                pass

        if self._current_target and sip.isValid(self._current_target):
            try:
                if hasattr(self._current_target, "clear_drop_indicator"):
                    self._current_target.clear_drop_indicator()
            except RuntimeError:
                pass

        self._is_dragging = False
        self._source_data = None
        self._current_target = None
        self._source_widget = None
