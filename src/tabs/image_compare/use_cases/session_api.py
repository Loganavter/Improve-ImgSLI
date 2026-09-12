"""Session API mixin — delegation shims for SessionController (Phase 4)."""

from __future__ import annotations

from typing import Any

from core.state_management.actions import SetChannelViewModeAction, SetDiffModeAction, SetInteractiveModeAction
from core.events import CoreUpdateRequestedEvent
from tabs.image_compare.events import AnalysisSetChannelViewModeEvent, AnalysisSetDiffModeEvent
from tabs.image_compare.use_cases import list_ops, navigation


class SessionApiMixin:
    # view modes
    def toggle_diff_mode(self, checked: bool):
        dispatcher = self.store.get_dispatcher()
        dispatcher.dispatch(SetInteractiveModeAction(checked), scope="viewport")
        self.store.emit_state_change("viewport")
    def set_diff_mode(self, mode: str):
        if self.store.viewport.view_state.diff_mode == mode: return
        dispatcher = self.store.get_dispatcher()
        dispatcher.dispatch(SetDiffModeAction(mode), scope="viewport")
        if self.diff_service is not None: self.diff_service.invalidate()
        if mode == "off" and self.event_bus: self.event_bus.emit(CoreUpdateRequestedEvent())
        self._trigger_metrics_calculation_if_needed()
        self.store.invalidate_render_cache()
        self.store.emit_state_change("viewport")
    def set_channel_view_mode(self, mode: str):
        if self.store.viewport.view_state.channel_view_mode == mode: return
        dispatcher = self.store.get_dispatcher()
        dispatcher.dispatch(SetChannelViewModeAction(mode), scope="viewport")
        if self.store.viewport.view_state.diff_mode != "off" and self.diff_service is not None: self.diff_service.invalidate()
        self.store.invalidate_render_cache()
        self.store.emit_state_change("viewport")
        if self.event_bus: self.event_bus.emit(CoreUpdateRequestedEvent())
    def on_set_channel_view_mode(self, event: AnalysisSetChannelViewModeEvent): self.set_channel_view_mode(event.mode)
    def on_set_diff_mode(self, event: AnalysisSetDiffModeEvent): self.set_diff_mode(event.mode)
    def on_metrics_requested_event(self, event: Any) -> None:
        payload = event.payload or {}
        if self.metrics_service is not None: self.metrics_service.calculate_metrics_async(payload.get("psnr", True), payload.get("ssim", True))
    # list/navigation delegates
    def swap_current_images(self): list_ops.swap_current_images(self)
    def swap_entire_lists(self): list_ops.swap_entire_lists(self)
    def remove_current_image_from_list(self, image_number: int): list_ops.remove_current_image_from_list(self, image_number)
    def remove_specific_image_from_list(self, image_number: int, index_to_remove: int): list_ops.remove_specific_image_from_list(self, image_number, index_to_remove)
    def clear_image_list(self, image_number: int): list_ops.clear_image_list(self, image_number)
    def reorder_item_in_list(self, image_number: int, source_index: int, dest_index: int): list_ops.reorder_item_in_list(self, image_number, source_index, dest_index)
    def reorder_items_in_list(self, *, list_num: int, indices, dest_index: int): list_ops.reorder_items_in_list(self, list_num=list_num, indices=indices, dest_index=dest_index)
    def move_item_between_lists(self, source_list_num: int, source_index: int, dest_list_num: int, dest_index: int): list_ops.move_item_between_lists(self, source_list_num, source_index, dest_list_num, dest_index)
    def move_items_between_lists(self, *, source_list_num: int, indices, dest_list_num: int, dest_index: int): list_ops.move_items_between_lists(self, source_list_num=source_list_num, indices=indices, dest_list_num=dest_list_num, dest_index=dest_index)
    def on_edit_name_changed(self, image_number, new_name): list_ops.on_edit_name_changed(self, image_number, new_name)
    def rename_image_at_index(self, image_number: int, index: int, new_name: str): list_ops.rename_image_at_index(self, image_number, index, new_name)
    def activate_single_image_mode(self, image_number: int): navigation.activate_single_image_mode(self, image_number)
    def deactivate_single_image_mode(self): navigation.deactivate_single_image_mode(self)
    def increment_rating(self, image_number: int, index: int): list_ops.increment_rating(self, image_number, index)
    def decrement_rating(self, image_number: int, index: int): list_ops.decrement_rating(self, image_number, index)
    def set_rating(self, image_number: int, index_to_set: int, new_score: int): list_ops.set_rating(self, image_number, index_to_set, new_score)
    def set_crop_override_at_index(self, image_number: int, index: int, value: bool | None): list_ops.set_crop_override_at_index(self, image_number, index, value)
    def on_combobox_changed(self, image_number: int, index: int, scroll_delta: int = 0): navigation.on_combobox_changed(self, image_number, index, scroll_delta)
    def on_interpolation_changed(self, index: int): navigation.on_interpolation_changed(self, index)
