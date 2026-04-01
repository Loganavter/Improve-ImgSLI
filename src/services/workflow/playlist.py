from core.store import Store
from services.workflow.playlist_components import (
    PlaylistListOperations,
    PlaylistMetadataController,
)

class PlaylistManager:
    def __init__(self, store: Store, main_controller=None):
        self.store = store
        self.main_controller = main_controller
        self.list_operations = PlaylistListOperations(
            store,
            main_controller=main_controller,
            set_current_image_callback=self._call_set_current_image,
            trigger_metrics_callback=self._trigger_metrics_calculation_if_needed,
        )
        self.metadata = PlaylistMetadataController(
            store,
            main_controller=main_controller,
        )

    def swap_current_images(self):
        self.list_operations.swap_current_images()

    def swap_entire_lists(self):
        self.list_operations.swap_entire_lists()

    def remove_current_image_from_list(self, image_number: int):
        self.list_operations.remove_current_image_from_list(image_number)

    def remove_specific_image_from_list(self, image_number: int, index_to_remove: int):
        self.list_operations.remove_specific_image_from_list(
            image_number, index_to_remove
        )

    def clear_image_list(self, image_number: int):
        self.list_operations.clear_image_list(image_number)

    def reorder_item_in_list(
        self, image_number: int, source_index: int, dest_index: int
    ):
        self.list_operations.reorder_item_in_list(image_number, source_index, dest_index)

    def move_item_between_lists(
        self,
        source_list_num: int,
        source_index: int,
        dest_list_num: int,
        dest_index: int,
    ):
        self.list_operations.move_item_between_lists(
            source_list_num, source_index, dest_list_num, dest_index
        )

    def _call_set_current_image(self, image_number: int, emit_signal: bool = True):
        if hasattr(self.store, "set_current_image"):
            self.store.set_current_image(image_number, emit_signal=emit_signal)
            return

        controller = self.main_controller
        if controller is not None and hasattr(controller, "set_current_image"):
            controller.set_current_image(image_number, emit_signal=emit_signal)
            return

        sessions = getattr(controller, "sessions", None) if controller is not None else None
        if sessions is not None and hasattr(sessions, "set_current_image"):
            sessions.set_current_image(image_number, emit_signal=emit_signal)
            return

        self.store.state_changed.emit("document")

    def _trigger_metrics_calculation_if_needed(self):
        if hasattr(self.store, "_trigger_metrics_calculation_if_needed"):
            self.store._trigger_metrics_calculation_if_needed()
        else:
            self.store.state_changed.emit("document")

    def increment_rating(self, image_number: int, index: int):
        self.metadata.increment_rating(image_number, index)

    def decrement_rating(self, image_number: int, index: int):
        self.metadata.decrement_rating(image_number, index)

    def set_rating(self, image_number: int, index_to_set: int, new_score: int):
        self.metadata.set_rating(image_number, index_to_set, new_score)

    def on_edit_name_changed(self, image_number, new_name):
        self.metadata.on_edit_name_changed(image_number, new_name)
