import logging
from typing import Optional
from PyQt6.QtCore import QTimer

from core.store import Store, ImageItem
from resources.translations import tr

logger = logging.getLogger("ImproveImgSLI")

class PlaylistManager:
    def __init__(self, store: Store, main_controller=None):
        self.store = store
        self.main_controller = main_controller

    def _get_presenter(self):

        if self.main_controller and hasattr(self.main_controller, 'presenter') and self.main_controller.presenter:
            return self.main_controller.presenter
        return None

    def swap_current_images(self):
        idx1, idx2 = self.store.document.current_index1, self.store.document.current_index2
        list1, list2 = self.store.document.image_list1, self.store.document.image_list2

        if not (0 <= idx1 < len(list1) and 0 <= idx2 < len(list2)):
            return

        list1[idx1], list2[idx2] = list2[idx2], list1[idx1]

        self.store.document.preview_image1, self.store.document.preview_image2 = (
            self.store.document.preview_image2,
            self.store.document.preview_image1
        )
        self.store.document.original_image1, self.store.document.original_image2 = (
            self.store.document.original_image2,
            self.store.document.original_image1
        )
        self.store.document.full_res_image1, self.store.document.full_res_image2 = (
            self.store.document.full_res_image2,
            self.store.document.full_res_image1
        )

        self.store.document.image1_path, self.store.document.image2_path = (
            self.store.document.image2_path,
            self.store.document.image1_path
        )

        self.store.viewport.display_cache_image1, self.store.viewport.display_cache_image2 = (
            self.store.viewport.display_cache_image2,
            self.store.viewport.display_cache_image1
        )

        self.store.viewport.scaled_image1_for_display, self.store.viewport.scaled_image2_for_display = (
            self.store.viewport.scaled_image2_for_display,
            self.store.viewport.scaled_image1_for_display
        )

        self.store.viewport.image1, self.store.viewport.image2 = (
            self.store.viewport.image2, self.store.viewport.image1
        )

        self.store.invalidate_geometry_cache()

        if self.main_controller:
            self.main_controller.ui_update_requested.emit(['combobox', 'file_names', 'resolution'])

        self._trigger_metrics_calculation_if_needed()
        self.store.state_changed.emit("document")

    def swap_entire_lists(self):
        self.store.swap_all_image_data()

        if self.main_controller:
            self.main_controller.ui_update_requested.emit(['combobox', 'file_names', 'resolution'])

    def remove_current_image_from_list(self, image_number: int):
        target_list, current_index = (
            (self.store.document.image_list1, self.store.document.current_index1)
            if image_number == 1
            else (self.store.document.image_list2, self.store.document.current_index2)
        )
        if not (0 <= current_index < len(target_list)):
            return

        path1_before = self.store.document.image1_path
        path2_before = self.store.document.image2_path

        target_list.pop(current_index)

        if path1_before and path2_before:
            cache_key = (path1_before, path2_before)
            self.store.viewport.session_data.unified_image_cache.pop(cache_key, None)

        new_list_len = len(target_list)
        new_index = min(current_index, new_list_len - 1) if new_list_len > 0 else -1

        if image_number == 1:
            self.store.document.current_index1 = new_index
        else:
            self.store.document.current_index2 = new_index

        self.store.invalidate_geometry_cache()

        if self.main_controller:
            self.main_controller.ui_update_requested.emit(['combobox', 'file_names', 'resolution'])
        self._trigger_metrics_calculation_if_needed()

        self._call_set_current_image(image_number)

    def remove_specific_image_from_list(self, image_number: int, index_to_remove: int):
        target_list, current_index = (
            (self.store.document.image_list1, self.store.document.current_index1)
            if image_number == 1
            else (self.store.document.image_list2, self.store.document.current_index2)
        )

        if not (0 <= index_to_remove < len(target_list)):
            return

        path1_before = self.store.document.image1_path
        path2_before = self.store.document.image2_path

        target_list.pop(index_to_remove)

        if path1_before and path2_before:
            cache_key = (path1_before, path2_before)
            self.store.viewport.session_data.unified_image_cache.pop(cache_key, None)

        new_list_len = len(target_list)
        new_current_index = current_index

        if new_list_len == 0:
            new_current_index = -1
        elif index_to_remove < current_index:
            new_current_index = current_index - 1
        elif index_to_remove == current_index:
            new_current_index = min(index_to_remove, new_list_len - 1)

        if image_number == 1:
            self.store.document.current_index1 = new_current_index
        else:
            self.store.document.current_index2 = new_current_index

        self.store.invalidate_geometry_cache()

        if self.main_controller:
            self.main_controller.ui_update_requested.emit(['combobox'])

        self._call_set_current_image(image_number)

    def clear_image_list(self, image_number: int):

        self.store.clear_all_caches()

        if image_number == 1:
            self.store.document.image_list1.clear()
            self.store.document.current_index1 = -1
        else:
            self.store.document.image_list2.clear()
            self.store.document.current_index2 = -1
        self.store.clear_image_slot_data(image_number)

        if self.main_controller:
            self.main_controller.ui_update_requested.emit(['combobox', 'file_names', 'resolution'])
        self.store.state_changed.emit("document")

    def reorder_item_in_list(self, image_number: int, source_index: int, dest_index: int):
        target_list = self.store.document.image_list1 if image_number == 1 else self.store.document.image_list2

        if not (0 <= source_index < len(target_list)):
            return

        if source_index < dest_index:
            dest_index -= 1

        item_to_move = target_list.pop(source_index)
        target_list.insert(dest_index, item_to_move)

        current_index = self.store.document.current_index1 if image_number == 1 else self.store.document.current_index2

        new_current_index = -1
        if current_index == source_index:
            new_current_index = dest_index
        elif source_index < current_index and dest_index >= current_index:
            new_current_index = current_index - 1
        elif source_index > current_index and dest_index <= current_index:
            new_current_index = current_index + 1
        else:
            new_current_index = current_index

        if image_number == 1:
            self.store.document.current_index1 = new_current_index
        else:
            self.store.document.current_index2 = new_current_index

        if self.main_controller:
            self.main_controller.ui_update_requested.emit(['combobox'])

    def move_item_between_lists(self, source_list_num: int, source_index: int, dest_list_num: int, dest_index: int):
        source_list = self.store.document.image_list1 if source_list_num == 1 else self.store.document.image_list2
        dest_list = self.store.document.image_list1 if dest_list_num == 1 else self.store.document.image_list2

        if not (0 <= source_index < len(source_list)):
            return

        path1_before = self.store.document.image_list1[self.store.document.current_index1].path if 0 <= self.store.document.current_index1 < len(self.store.document.image_list1) else None
        path2_before = self.store.document.image_list2[self.store.document.current_index2].path if 0 <= self.store.document.current_index2 < len(self.store.document.image_list2) else None

        item_to_move = source_list.pop(source_index)
        src_path_moved = item_to_move.path if item_to_move else None

        existing_dest_idx = -1
        if src_path_moved:
            for i, it in enumerate(dest_list):
                if it.path == src_path_moved:
                    existing_dest_idx = i
                    break

        if existing_dest_idx != -1:
            dest_list.pop(existing_dest_idx)
            if existing_dest_idx < dest_index:
                dest_index -= 1

        dest_index = max(0, min(dest_index, len(dest_list)))
        dest_list.insert(dest_index, item_to_move)

        new_idx1 = -1
        if path1_before:
            try:
                new_idx1 = next(i for i, item in enumerate(self.store.document.image_list1) if item.path == path1_before)
            except StopIteration:
                pass
        if new_idx1 == -1 and len(self.store.document.image_list1) > 0:
            new_idx1 = 0
            if source_list_num == 1 and source_index == self.store.document.current_index1:
                 new_idx1 = min(source_index, len(self.store.document.image_list1) - 1)

        new_idx2 = -1
        if path2_before:
            try:
                new_idx2 = next(i for i, item in enumerate(self.store.document.image_list2) if item.path == path2_before)
            except StopIteration:
                pass
        if new_idx2 == -1 and len(self.store.document.image_list2) > 0:
            new_idx2 = 0
            if source_list_num == 2 and source_index == self.store.document.current_index2:
                 new_idx2 = min(source_index, len(self.store.document.image_list2) - 1)

        self.store.document.current_index1 = new_idx1
        self.store.document.current_index2 = new_idx2

        if self.main_controller:
            self.main_controller.ui_update_requested.emit(['combobox'])
        self._call_set_current_image(1, emit_signal=False)
        self._call_set_current_image(2, emit_signal=False)

        self.store.state_changed.emit("document")

    def _call_set_current_image(self, image_number: int, emit_signal: bool = True):

        if hasattr(self.store, 'set_current_image'):
            self.store.set_current_image(image_number, emit_signal=emit_signal)
        else:

            if self.main_controller and self.main_controller.session_ctrl:
                self.main_controller.session_ctrl.set_current_image(image_number, emit_signal=emit_signal)
            else:
                self.store.state_changed.emit("document")

    def _trigger_metrics_calculation_if_needed(self):
        if hasattr(self.store, '_trigger_metrics_calculation_if_needed'):
            self.store._trigger_metrics_calculation_if_needed()
        else:
            self.store.state_changed.emit("document")

    def increment_rating(self, image_number: int, index: int):
        self._change_rating(image_number, index, 1)

    def decrement_rating(self, image_number: int, index: int):
        self._change_rating(image_number, index, -1)

    def set_rating(self, image_number: int, index_to_set: int, new_score: int):
        target_list = (
            self.store.document.image_list1
            if image_number == 1
            else self.store.document.image_list2
        )
        current_index = (
            self.store.document.current_index1
            if image_number == 1
            else self.store.document.current_index2
        )
        if not (0 <= index_to_set < len(target_list)):
            return
        item = target_list[index_to_set]
        item.rating = new_score

        if index_to_set == current_index:

            if self.main_controller:
                self.main_controller.ui_update_requested.emit(['ratings'])

    def _change_rating(self, image_number: int, index_to_change: int, delta: int):
        target_list = (
            self.store.document.image_list1
            if image_number == 1
            else self.store.document.image_list2
        )
        current_index = (
            self.store.document.current_index1
            if image_number == 1
            else self.store.document.current_index2
        )
        if not (0 <= index_to_change < len(target_list)):
            return
        item = target_list[index_to_change]
        item.rating += delta

        from PyQt6.QtCore import QTimer

        if index_to_change == current_index:
            if self.main_controller:

                self.main_controller.ui_update_requested.emit(['ratings'])

        def _update_flyout():
            if hasattr(self.main_controller, 'presenter') and self.main_controller.presenter:
                ui_manager = getattr(self.main_controller.presenter, 'ui_manager', None)
                if ui_manager and hasattr(ui_manager, 'unified_flyout'):
                    flyout = ui_manager.unified_flyout
                    if flyout and flyout.isVisible():
                        flyout.update_rating_for_item(image_number, index_to_change)

        QTimer.singleShot(0, _update_flyout)

    def on_edit_name_changed(self, image_number, new_name):
        new_name = new_name.strip()
        target_list = (
            self.store.document.image_list1
            if image_number == 1
            else self.store.document.image_list2
        )
        idx = self.store.document.current_index1 if image_number == 1 else self.store.document.current_index2

        if 0 <= idx < len(target_list):
            item = target_list[idx]
            if new_name != item.display_name:

                item.display_name = new_name

                self.store.state_changed.emit("document")
                if self.main_controller:
                    self.main_controller.ui_update_requested.emit(['combobox'])
