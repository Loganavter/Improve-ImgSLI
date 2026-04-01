from __future__ import annotations

from PyQt6.QtCore import QTimer

from services.workflow.playlist_components.common import (
    emit_ui_update,
    get_current_index,
    get_presenter,
    get_target_list,
)

class PlaylistMetadataController:
    def __init__(self, store, main_controller=None):
        self.store = store
        self.main_controller = main_controller

    def increment_rating(self, image_number: int, index: int) -> None:
        self._change_rating(image_number, index, 1)

    def decrement_rating(self, image_number: int, index: int) -> None:
        self._change_rating(image_number, index, -1)

    def set_rating(self, image_number: int, index_to_set: int, new_score: int) -> None:
        target_list = get_target_list(self.store, image_number)
        current_index = get_current_index(self.store, image_number)
        if not (0 <= index_to_set < len(target_list)):
            return

        target_list[index_to_set].rating = new_score
        if index_to_set == current_index:
            emit_ui_update(self.main_controller, ["ratings"])

    def on_edit_name_changed(self, image_number, new_name) -> None:
        target_list = get_target_list(self.store, image_number)
        current_index = get_current_index(self.store, image_number)
        new_name = new_name.strip()

        if 0 <= current_index < len(target_list):
            item = target_list[current_index]
            if new_name != item.display_name:
                item.display_name = new_name
                self.store.state_changed.emit("document")
                emit_ui_update(self.main_controller, ["combobox"])

    def _change_rating(self, image_number: int, index_to_change: int, delta: int) -> None:
        target_list = get_target_list(self.store, image_number)
        current_index = get_current_index(self.store, image_number)
        if not (0 <= index_to_change < len(target_list)):
            return

        item = target_list[index_to_change]
        item.rating += delta

        if index_to_change == current_index:
            emit_ui_update(self.main_controller, ["ratings"])

        QTimer.singleShot(
            0,
            lambda: self._update_visible_flyout_rating(image_number, index_to_change),
        )

    def _update_visible_flyout_rating(self, image_number: int, index_to_change: int) -> None:
        presenter = get_presenter(self.main_controller)
        if presenter is None:
            return
        ui_manager = getattr(presenter, "ui_manager", None)
        if ui_manager and hasattr(ui_manager, "unified_flyout"):
            flyout = ui_manager.unified_flyout
            if flyout and flyout.isVisible():
                flyout.update_rating_for_item(image_number, index_to_change)
