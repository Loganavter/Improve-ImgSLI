from PyQt6.QtCore import QTimer

class _UnifiedFlyoutSessionMixin:
    def _schedule_structure_sync(self):
        QTimer.singleShot(0, lambda: self.sync_from_store())

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
        session_handler = self._get_session_handler()
        if session_handler is not None and hasattr(
            session_handler, "remove_specific_image_from_list"
        ):
            session_handler.remove_specific_image_from_list(list_num, index)

    def _get_current_index(self, image_number: int) -> int:
        if image_number == 1:
            return self.store.document.current_index1
        if image_number == 2:
            return self.store.document.current_index2
        return -1

    def _get_item_rating(self, image_number: int, index: int) -> int:
        target_list = (
            self.store.document.image_list1
            if image_number == 1
            else self.store.document.image_list2
        )
        if 0 <= index < len(target_list):
            return getattr(target_list[index], "rating", 0)
        return 0

    def _create_rating_gesture(
        self, image_number: int, item_index: int, starting_score: int
    ):
        if self.main_controller is None:
            return None
        from shared_toolkit.ui.gesture_resolver import RatingGestureTransaction

        return RatingGestureTransaction(
            main_controller=self.main_controller,
            image_number=image_number,
            item_index=item_index,
            starting_score=starting_score,
        )

    def _increment_rating(self, image_number: int, index: int) -> None:
        session_handler = self._get_session_handler()
        if session_handler is not None and hasattr(session_handler, "increment_rating"):
            session_handler.increment_rating(image_number, index)

    def _decrement_rating(self, image_number: int, index: int) -> None:
        session_handler = self._get_session_handler()
        if session_handler is not None and hasattr(session_handler, "decrement_rating"):
            session_handler.decrement_rating(image_number, index)

    def _reorder_item(self, image_number: int, source_index: int, dest_index: int) -> None:
        session_handler = self._get_session_handler()
        if session_handler is not None and hasattr(
            session_handler, "reorder_item_in_list"
        ):
            session_handler.reorder_item_in_list(
                image_number=image_number,
                source_index=source_index,
                dest_index=dest_index,
            )
            self._schedule_structure_sync()

    def _move_item_between_lists(
        self,
        source_list_num: int,
        source_index: int,
        dest_list_num: int,
        dest_index: int,
    ) -> None:
        session_handler = self._get_session_handler()
        if session_handler is not None and hasattr(
            session_handler, "move_item_between_lists"
        ):
            session_handler.move_item_between_lists(
                source_list_num=source_list_num,
                source_index=source_index,
                dest_list_num=dest_list_num,
                dest_index=dest_index,
            )
            self._schedule_structure_sync()
