from __future__ import annotations

from services.workflow.playlist_components.common import (
    emit_ui_update,
    find_index_by_path,
    get_current_item_path,
    get_current_index,
    get_target_list,
    set_current_index,
)

class PlaylistListOperations:
    def __init__(
        self,
        store,
        main_controller=None,
        set_current_image_callback=None,
        trigger_metrics_callback=None,
    ):
        self.store = store
        self.main_controller = main_controller
        self._set_current_image = set_current_image_callback
        self._trigger_metrics = trigger_metrics_callback

    def swap_current_images(self) -> None:
        idx1 = self.store.document.current_index1
        idx2 = self.store.document.current_index2
        list1 = self.store.document.image_list1
        list2 = self.store.document.image_list2
        if not (0 <= idx1 < len(list1) and 0 <= idx2 < len(list2)):
            return

        list1[idx1], list2[idx2] = list2[idx2], list1[idx1]

        self.store.document.preview_image1, self.store.document.preview_image2 = (
            self.store.document.preview_image2,
            self.store.document.preview_image1,
        )
        self.store.document.original_image1, self.store.document.original_image2 = (
            self.store.document.original_image2,
            self.store.document.original_image1,
        )
        self.store.document.full_res_image1, self.store.document.full_res_image2 = (
            self.store.document.full_res_image2,
            self.store.document.full_res_image1,
        )
        self.store.document.image1_path, self.store.document.image2_path = (
            self.store.document.image2_path,
            self.store.document.image1_path,
        )
        self.store.viewport.session_data.render_cache.display_cache_image1, self.store.viewport.session_data.render_cache.display_cache_image2 = (
            self.store.viewport.session_data.render_cache.display_cache_image2,
            self.store.viewport.session_data.render_cache.display_cache_image1,
        )
        (
            self.store.viewport.session_data.render_cache.scaled_image1_for_display,
            self.store.viewport.session_data.render_cache.scaled_image2_for_display,
        ) = (
            self.store.viewport.session_data.render_cache.scaled_image2_for_display,
            self.store.viewport.session_data.render_cache.scaled_image1_for_display,
        )
        self.store.viewport.session_data.image_state.image1, self.store.viewport.session_data.image_state.image2 = (
            self.store.viewport.session_data.image_state.image2,
            self.store.viewport.session_data.image_state.image1,
        )

        self.store.invalidate_geometry_cache()
        emit_ui_update(self.main_controller, ["combobox", "file_names", "resolution"])
        self._emit_metrics_update()
        self.store.state_changed.emit("document")

    def swap_entire_lists(self) -> None:
        self.store.swap_all_image_data()
        emit_ui_update(self.main_controller, ["combobox", "file_names", "resolution"])

    def remove_current_image_from_list(self, image_number: int) -> None:
        target_list = get_target_list(self.store, image_number)
        current_index = get_current_index(self.store, image_number)
        if not (0 <= current_index < len(target_list)):
            return

        self._evict_unified_cache_entry()
        target_list.pop(current_index)

        new_index = min(current_index, len(target_list) - 1) if target_list else -1
        set_current_index(self.store, image_number, new_index)

        self.store.invalidate_geometry_cache()
        emit_ui_update(self.main_controller, ["combobox", "file_names", "resolution"])
        self._emit_metrics_update()
        self._set_current_image(image_number)

    def remove_specific_image_from_list(
        self, image_number: int, index_to_remove: int
    ) -> None:
        target_list = get_target_list(self.store, image_number)
        current_index = get_current_index(self.store, image_number)
        if not (0 <= index_to_remove < len(target_list)):
            return

        self._evict_unified_cache_entry()
        target_list.pop(index_to_remove)

        if not target_list:
            new_current_index = -1
        elif index_to_remove < current_index:
            new_current_index = current_index - 1
        elif index_to_remove == current_index:
            new_current_index = min(index_to_remove, len(target_list) - 1)
        else:
            new_current_index = current_index

        set_current_index(self.store, image_number, new_current_index)
        self.store.invalidate_geometry_cache()
        emit_ui_update(self.main_controller, ["combobox"])
        self._set_current_image(image_number)

    def clear_image_list(self, image_number: int) -> None:
        self.store.clear_all_caches()
        target_list = get_target_list(self.store, image_number)
        target_list.clear()
        set_current_index(self.store, image_number, -1)
        self.store.clear_image_slot_data(image_number)

        emit_ui_update(self.main_controller, ["combobox", "file_names", "resolution"])
        self.store.state_changed.emit("document")

    def reorder_item_in_list(
        self, image_number: int, source_index: int, dest_index: int
    ) -> None:
        target_list = get_target_list(self.store, image_number)
        if not (0 <= source_index < len(target_list)):
            return

        if source_index < dest_index:
            dest_index -= 1

        item_to_move = target_list.pop(source_index)
        target_list.insert(dest_index, item_to_move)

        current_index = get_current_index(self.store, image_number)
        if current_index == source_index:
            new_current_index = dest_index
        elif source_index < current_index and dest_index >= current_index:
            new_current_index = current_index - 1
        elif source_index > current_index and dest_index <= current_index:
            new_current_index = current_index + 1
        else:
            new_current_index = current_index

        set_current_index(self.store, image_number, new_current_index)
        emit_ui_update(self.main_controller, ["combobox"])

    def move_item_between_lists(
        self,
        source_list_num: int,
        source_index: int,
        dest_list_num: int,
        dest_index: int,
    ) -> None:
        source_list = get_target_list(self.store, source_list_num)
        dest_list = get_target_list(self.store, dest_list_num)
        if not (0 <= source_index < len(source_list)):
            return

        path1_before = get_current_item_path(self.store, 1)
        path2_before = get_current_item_path(self.store, 2)

        item_to_move = source_list.pop(source_index)
        source_path = item_to_move.path if item_to_move else None

        existing_dest_idx = find_index_by_path(dest_list, source_path)
        if existing_dest_idx != -1:
            dest_list.pop(existing_dest_idx)
            if existing_dest_idx < dest_index:
                dest_index -= 1

        dest_index = max(0, min(dest_index, len(dest_list)))
        dest_list.insert(dest_index, item_to_move)

        set_current_index(
            self.store,
            1,
            self._resolve_current_index_after_cross_move(1, path1_before, source_list_num, source_index),
        )
        set_current_index(
            self.store,
            2,
            self._resolve_current_index_after_cross_move(2, path2_before, source_list_num, source_index),
        )

        emit_ui_update(self.main_controller, ["combobox"])
        self._set_current_image(1, emit_signal=False)
        self._set_current_image(2, emit_signal=False)
        self.store.state_changed.emit("document")

    def _resolve_current_index_after_cross_move(
        self, image_number: int, previous_path, source_list_num: int, source_index: int
    ) -> int:
        target_list = get_target_list(self.store, image_number)
        resolved_index = find_index_by_path(target_list, previous_path)
        if resolved_index != -1:
            return resolved_index
        if not target_list:
            return -1
        if source_list_num == image_number and source_index == get_current_index(self.store, image_number):
            return min(source_index, len(target_list) - 1)
        return 0

    def _evict_unified_cache_entry(self) -> None:
        path1_before = self.store.document.image1_path
        path2_before = self.store.document.image2_path
        if path1_before and path2_before:
            cache_key = (path1_before, path2_before)
            self.store.viewport.session_data.render_cache.unified_image_cache.pop(cache_key, None)

    def _emit_metrics_update(self) -> None:
        if self._trigger_metrics is not None:
            self._trigger_metrics()
