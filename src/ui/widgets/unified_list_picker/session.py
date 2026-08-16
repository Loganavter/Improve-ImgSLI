from PySide6.QtCore import QTimer

from sli_ui_toolkit.config import create_rating_gesture
from ui.widgets.unified_list_picker.common import (
    _UnifiedFlyoutBase,
    current_index_for_list,
    items_for_list,
)

class _UnifiedFlyoutSessionMixin(_UnifiedFlyoutBase):
    def _schedule_structure_sync(self):
        if self.isVisible() and not getattr(self, "_is_refreshing", False):
            self.sync_from_store()
            return

        if getattr(self, "_structure_sync_scheduled", False):
            return
        self._structure_sync_scheduled = True

        def _run_sync():
            self._structure_sync_scheduled = False
            self.sync_from_store()

        QTimer.singleShot(0, _run_sync)

    def _get_session_handler(self):
        controller = self.main_controller
        if controller is None:
            return None
        if hasattr(controller, "on_combobox_changed"):
            return controller
        return getattr(controller, "sessions", None)

    def _on_item_selected(self, list_num: int, index: int):
        if self._is_simple_mode:
            self.simple_item_chosen.emit(index)
        else:
            session_handler = self._get_session_handler()
            if session_handler is not None and hasattr(
                session_handler, "on_combobox_changed"
            ):
                session_handler.on_combobox_changed(list_num, index)
            self.item_chosen.emit(list_num, index)
        self.start_closing_animation()

    def _on_item_right_clicked(self, list_num, index):
        """Forward right-click to the host; do not delete the row here.

        Hosts that want a context menu connect ``item_context_menu_requested``.
        ``create_double_list`` wires a remove fallback for standalone demos.
        """
        self.item_context_menu_requested.emit(list_num, index)

    def _get_current_index(self, list_num: int) -> int:
        return current_index_for_list(self._document(), list_num)

    def _get_item_rating(self, list_num: int, index: int) -> int:
        target_list = items_for_list(self._document(), list_num)
        if 0 <= index < len(target_list):
            return getattr(target_list[index], "rating", 0)
        return 0

    def _create_rating_gesture(
        self, list_num: int, item_index: int, starting_score: int
    ):
        if self.main_controller is None:
            return None
        # Pass both names: hosts may still expect ``image_number``.
        return create_rating_gesture(
            main_controller=self.main_controller,
            list_num=list_num,
            image_number=list_num,
            item_index=item_index,
            starting_score=starting_score,
        )

    def _increment_rating(self, list_num: int, index: int) -> None:
        session_handler = self._get_session_handler()
        if session_handler is not None and hasattr(session_handler, "increment_rating"):
            session_handler.increment_rating(list_num, index)

    def _decrement_rating(self, list_num: int, index: int) -> None:
        session_handler = self._get_session_handler()
        if session_handler is not None and hasattr(session_handler, "decrement_rating"):
            session_handler.decrement_rating(list_num, index)

    def _reorder_item(self, list_num: int, indices, dest_index: int) -> None:
        if isinstance(indices, int):
            indices = [indices]
        session_handler = self._get_session_handler()
        if session_handler is None:
            return
        if hasattr(session_handler, "reorder_items_in_list"):
            session_handler.reorder_items_in_list(
                list_num=list_num,
                indices=list(indices),
                dest_index=dest_index,
            )
            self._schedule_structure_sync()
            return
        if hasattr(session_handler, "reorder_item_in_list") and indices:
            from sli_ui_toolkit.ui.widgets.helpers.multi_move import normalize_indices

            normalized = normalize_indices(indices)
            if not normalized:
                return
            session_handler.reorder_item_in_list(
                list_num, normalized[0], dest_index
            )
            self._schedule_structure_sync()

    def _move_item_between_lists(
        self,
        source_list_num: int,
        indices,
        dest_list_num: int,
        dest_index: int,
    ) -> None:
        if isinstance(indices, int):
            indices = [indices]
        session_handler = self._get_session_handler()
        if session_handler is None:
            return
        if hasattr(session_handler, "move_items_between_lists"):
            session_handler.move_items_between_lists(
                source_list_num=source_list_num,
                indices=list(indices),
                dest_list_num=dest_list_num,
                dest_index=dest_index,
            )
            self._schedule_structure_sync()
            return
        if hasattr(session_handler, "move_item_between_lists") and indices:
            from sli_ui_toolkit.ui.widgets.helpers.multi_move import normalize_indices

            normalized = normalize_indices(indices)
            insert_at = dest_index
            for index in sorted(normalized, reverse=True):
                session_handler.move_item_between_lists(
                    source_list_num=source_list_num,
                    source_index=index,
                    dest_list_num=dest_list_num,
                    dest_index=insert_at,
                )
            self._schedule_structure_sync()